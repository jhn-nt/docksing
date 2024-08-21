# DockSing
## CLI Utility for deployment of containerized slurm jobs on HPC 
### Requirements 
* _Local_: [Docker](https://www.docker.com/products/docker-desktop/)
* _Local_: `python>3.10`
* _Remote_: [Singularity](https://docs.sylabs.io/guides/2.6/user-guide/index.html)

### Installation
On your _local_ host run:
```bash
pip install git+https://gitlab-core.supsi.ch/dti-idsia/giovanni.angelotti/docksing.git
```
### Usage Tutorial
In an hypothetic scenario we have an dockerized expirement to run, based for the example on the following `Dockerfile`:
```dockerfile
FROM alpine:latest 
ENTRYPOINT ["echo"]
```
We then build the container image based on the above `Dockerfile` and we name it with tag `experiment` using standard docker practices:
```bash
docker build -t experiment .
```
We wish to run the experiment by passing it the arguments `["hello",">","output.txt"]`, so that running the container will produce as output a text file `output.txt`.   
We know that experiment will not need an heavy resources, one cpu node with one core on the remote HPC will suffice. Additionally, we wish to create an environment variable that will be needed to run our experiment. To achieve this we create a `config.yaml` file as follows:
```yaml
remotedir:  remote_directory

slurm:
  nodes: 1
  cpus-per-task: 1
  job-name: docksing_test

container:
  image:  experiment
  commands: ["hello",">","output.txt"]
  environment:
    - TEST: hello__world
    - GOOGLE_APPLICATION_CREDENTIALS: hello!
    - salerno: reggio_calabria
  ports:
    - 8080:8080
```
The `config.yaml` must have at _least_ three keys:
* `remotedir`: The absolute path of target folder as string on the remote host.  
* `slurm`: a key-value mapping that parametrises [options](https://slurm.schedmd.com/srun.html) to pass to `srun`.
* `container`: mapping parametrizing options to pass to  `docker run` or `singularity run`. Syntax squarely follows that of [docker-compose](https://docs.docker.com/compose/).


It is good practice to verify through a dry run that our code works properly:
```python
python3 -m docksing --ssh user.name@host --config config.yaml --local 
```
The above command will run everything locally for easier debugging.
If we do not encour in any error, we may deploy our job on the remote HPC, simply by removing the `--local` argument:
```python
python3 -m docksing --ssh user.name@host --config config.yaml
```

### Quick Overview
`DockSing` aims to simplify deployment of jobs on remote slurm clusters developed under the [devcontainers](https://code.visualstudio.com/docs/devcontainers/containers) philosophy, it may be less effective for other development designs.   
In essence `DockSing` automate four steps:
1. Pushes the local devcontainer image from the local docker daemon to the remote hpc.  
2. Converts the docker-based devcontainer image into a singularity instance on the remote hpc.  
3. Starts slurm job based on the options defined in the configuartion file.  
4. Passes to the singularity instanses all necessary infos required to run the code (such as enviornment variables, ports etc etc), as defined in the configuration file.  

### Design Notes
`DockSing` is developed with the aim of mainting the highest adherence to existing standards with the lowest code overhead possible, in order to retrospectively preserve interoperability with docker, singularity and SLURM documentations.  
To squeeze the most out of `DockSing` it is advisable to have good proficiency with the docker ecosystem.