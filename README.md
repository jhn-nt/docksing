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
### Usage
In an hypothetic scenario we have an expirement to run, based on the following `Dockerfile`:
```dockerfile
FROM alpine:latest 
ENTRYPOINT ["echo"]
```
We then build the container image based on the above `Dockerfile` and we name it `experiment` using standard docker practices:
```bash
docker build -t experiment .
```
We wish to run the experiment by passing it the arguments `["Hello!",">","docksing.txt"]`, so that running the container will produce as output a text file `docksing.txt`.   
We know that experiment will not need an heavy resources, one cpu node with one core on the remote HPC will suffice. Additionally, we wish to create an environment variable that will be needed to run our experiment. To achieve this we create a `config.json` file as follows:
```json
{
    "workdir":"a_docksing_example",
    "slurm":{"nodes":1,"cpus-per-task":1,"job-name":"docksing_test"},
    "docker":{"environment":{"TESTENV":"this is a test!"}},
    "commands":["Hello!",">","docksing.txt"]
}
```
The `config.json` must have at _least_ four keys:
* `"workdir"`: The absolute path of target folder as string on the remote host, If it doesn't exists it will be created.  
* `"slurm"`: A dictionary where each key is a slurm property with its respective value.
* `"docker"`: A dictionary where each key is a `docker run` property with its respective value.
* `"commands"`: Optional auxilliary commands to serve as, possibly, entrypoint executions of the image. 




It is good practice to verify through a dry run that our code works properly:
```python
python3 -m docksing --ssh user.name@host --config config.json --local experiment
```
If we do not encour in any error, we may deploy our job on the remote HPC, simply by removing the `--local` argument:
```python
python3 -m docksing --ssh user.name@host --config config.json experiment
```

### Design Notes
`DockSing` is developed with the aim of mainting the highest adherence to existing standards with the lowest code overhead possible, in order to retrospectively preserve interoperability with docker, singularity and SLURM documentations.  
To squeeze the most out of `DockSing` it is advisable to have good proficiency with the docker ecosystem.