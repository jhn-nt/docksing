# DockSing
## CLI Utility for deployment of containerized jobs on SLURM HPCs 
### Requirements 
* _Local_: [Docker](https://www.docker.com/products/docker-desktop/)
* _Local_: `python>3.10`
* _Remote_: [Singularity](https://docs.sylabs.io/guides/2.6/user-guide/index.html)

### Installation
On your _local_ host run:
```bash
pip install git+https://gitlab-core.supsi.ch/dti-idsia/giovanni.angelotti/docksing.git
```
### What is _Docksing_?
_DockSing_ is a pure-python lightweight CLI tool to orchestrate deployment of jobs to docker and slurm end points based on the [compose specification](https://compose-spec.io/) and loosely inspired by [Google Vertex AI](https://cloud.google.com/vertex-ai/docs).

Deploying a job on a local docker:
```bash
docksing --ssh username@hostname --config config.yaml --local
```

Deploying a job on a remote Slurm HPC:
```bash
docksing --ssh username@hostname --config config.yaml 
```
### Why _DockSing_?
_DockSing_ exists to reduce the overhead effort required to scale from development to testing to deployment of experiments.
Specifically, _DockSing_ takes care of automatically converting docker-compose specifications to singularity specifications overloaded with SBATCH commands, lifting us from dealing with the nuisances of mapping and combining the three.

### Who is _Docksing_ for?
_DockSing_ aims to simplify the experimentation workflow for those using docker and more specifically [devcontainers](https://code.visualstudio.com/docs/devcontainers/containers). 


### Overview
Just like docker-compose, Docksing requires a `config.yaml` to initiate a job.  
This `config.yaml`, however, slightly differs from a typical `docker-compose` file in that it is split in three _chapters_: 
1. `remotedir`: Path to the target directory that will be created in the remote host. All files required to run the job, comprising of `.sif` images, bind maps and eventual job outputs will be stored here. 
2. `slurm`: Chapter of `key:value` maps encoding `srun` options ([reference](https://slurm.schedmd.com/srun.html)).
3. `container`: Chapter containing all entries one would use in a normal `docker-compose` file. Note that Docksing only supports some limited docker-compose functionalities, please refer to the supported compose specification section below.


```yml
  remotedir:  path/to/remote/direcotry
  slurm:
    nodes:  1
    cpus-per-task:  1
    job-name: job-name
  container:
    image:  tag
    commands: ["sh -c","'echo Hello World'"]
    environment:
    - env_variable: env_content
    - another_env_variable: another_env_content  
    volumes:
    - /absolute/path/to/bind:/container/path/to/bind
    - /another/absolute/path/to/bind:another/container/path/to/bind
```

To launch the job then run:
```bash
docksing --ssh username@hostname --config path/to/config.yaml 
```
Essentially the above commands automate the follwoing actions, in order:
1.  Attempts to establish a connection through SSH to the remote host
2.  Attempts to establish a connection to the local docker daemon
3.  Verifies that the image `tag` is available in the local docker daemon 
4.  Creates the `remotedir` in the remote host
5.  Copies the image `tag` pulled from the local docker daemon to the `remotedir`
6.  Copies the content of all source binds in `volumes` from the local host to the remote host
7.  Converts the image `tag` in a `.sif` build, compatible with singularity  
8.  Starts the `srun` job by passing all options found in the `slurm` chapter while also passing all options found in `container` to the nested `singularity run` 

A side note, steps 7 and 8 and executed within the same `srun` instance to minimize queues on the remote.



### Tutorial
Assume we have the following `config.yaml`:
```yml
remotedir:  target_directory_on_remote_host

slurm:
  nodes: 1
  cpus-per-task: 1
  job-name: name_of_the_slurm_job

container:
  image:  alpine:latest
  commands: ["sh -c","'echo the $VARIABLE is $VALUE   > /output/result.txt'"]
  environment:
    - VARIABLE: color
    - GOOGLE_APPLICATION_CREDENTIALS: credentials
    - VALUE: red
  volumes:
    - /absolute/path/to/output:/output

```
First and foremost, we pull the image (or build the dockerfile) required to run the job:
```bash
docker pull alpine:latest
```
DockSing will raise an error if it cannot find the image in the local docker daemon.  
Afterwords we should assert whether our setup is correct, through:
```bash
docksing --ssh username@hostname --config config.yaml --cli --local
```
Which returns:
```bash
docker run --env VARIABLE=color --env GOOGLE_APPLICATION_CREDENTIALS=credentials --env VALUE=red --volume /absolute/path/to/output:/output alpine:latest sh -c 'echo the $VARIABLE is $VALUE   > /output/result.txt'
```
If it does look right, we may proced to run a _local run_ to assess whether our logic is correct:
```bash
docksing --ssh username@hostname --config config.yaml --local
```
If it is, we likewise check whether our setup is correct in the remote case:
```bash
docksing --ssh username@hostname --config config.yaml --cli 
```
Which, again, returns:
```bash
srun --nodes=1 --cpus-per-task=1 --job-name=name_of_the_slurm_job bash -c "singularity build target_directory_on_remote_host/91ef0af61f39.sif docker-archive://target_directory_on_remote_host/91ef0af61f39.tar && singularity run --env VARIABLE=color --env GOOGLE_APPLICATION_CREDENTIALS=credentials --env VALUE=red --bind target_directory_on_remote_host/output:/output target_directory_on_remote_host/91ef0af61f39.sif sh -c 'echo the $VARIABLE is $VALUE   > /output/result.txt'"
```
Note how a simple docker run quickly explodes in complexity and verbosity when we need to deploy it remotely via SLURM on singularity, which may be prone to errors.  
If the command looks right, we may actually submit the job on the HPC via:
```bash
docksing --ssh username@hostname --config config.yaml 
```
Which lauches the job.  
Often, however, one may which to monitor the logs to assess how the job is going.
To do so, one can simply run:
```bash
docksing --ssh username@hostname --config config.yaml --stream 
```
Which streams the remote `stdout` and `stderr` to the current console.


### List of Features
1. Launching a local job on docker
```bash
docksing --ssh username@hostname --config config.yaml --local 
```
2. Launching a remote job
```bash
docksing --ssh username@hostname --config config.yaml --cli
```
3. Inspecting local cli
```bash
docksing --ssh username@hostname --config config.yaml --local --cli
```
4. Inspecting remote cli
```bash
docksing --ssh username@hostname --config config.yaml --cli
```
5. Stream the remote job logs to a local console
```bash
docksing --ssh username@hostname --config config.yaml --stream
```

### Supported Compose Specification
- workdir
- environment
- volumes
- commands

### Design Notes
DockSing is developed with the aim of mainting the highest adherence to existing standards with the lowest code overhead possible, in order to retrospectively preserve interoperability with docker, singularity and SLURM documentations.  
To squeeze the most out of DockSing it is advisable to have good proficiency with the docker ecosystem.

### Limitations
Docksing was tested on a Linux environment, milage may very on other systems.

