from __future__ import annotations
from dataclasses import dataclass, field
from paramiko import SSHClient, AutoAddPolicy, SFTPClient
from scp import SCPClient
import docker
from docker.client import DockerClient
from getpass import getpass
import io



@dataclass
class DockSing:
    ssh: SSHClient=field(repr=False)
    docker: DockerClient=field(repr=False)

    @classmethod
    def connect(cls,ssh:str)->DockSing:
        username,hostname=ssh.split("@")

        ssh_client=SSHClient()
        ssh_client.set_missing_host_key_policy(AutoAddPolicy())
        ssh_client.connect(hostname=hostname,username=username,password=getpass(f"Password for {ssh}:"))

        return cls(ssh=ssh_client,docker=docker.from_env())
    
    def setup(self,workdir:str):
        sftp=SFTPClient.from_transport(self.ssh.get_transport())
        try:
            sftp.stat(workdir)
        except:
            sftp.mkdir(workdir)
    
    def push(self,tag:str,workdir:str):
        image=self.docker.images.get(tag)
        iid=image.id.split(":")[1]
        with io.BytesIO() as file:
            for blob in image.save():
                file.write(blob)
            file.seek(0)
        
            with SCPClient(self.ssh.get_transport()) as scp:
                scp.putfo(file,f"{workdir}/{iid}.tar")

    
    def build(self,tag:str,workdir:str):
        image=self.docker.images.get(tag)
        iid=image.id.split(":")[1]
        self.ssh.exec_command(f"cd {workdir}; srun singularity build {iid}.sif docker-archive://{iid}.tar")


    def submit(self,tag:str,workdir:str,config):
        image=self.docker.images.get(tag)
        iid=image.id.split(":")[1]

        slurm_cmd="srun"+" ".join([f"{command}={value}" for (command,value) in config["slurm"].items()])
        docker_cmd="singularity run"+" ".join([f" {command}={value} " for (command,value) in config["docker"].items()])
        commands_cmd=" ".join([f" {command}={value} " for (command,value) in config["commands"].items()])
        self.ssh.exec_command(f"cd {workdir}; {slurm_cmd} {docker_cmd} {iid}.sif {commands_cmd}")
        

if __name__=="__main__":
    from argparse import ArgumentParser
    from tqdm import tqdm
    import json

    parser=ArgumentParser()

    parser.add_argument("--ssh",action="store",required=True)
    parser.add_argument("--config",action="store",required=True)
    parser.add_argument("tag",action="store")




    args,other=parser.parse_known_args()

    SSH=args.ssh
    CONFIG=json.load(open(args.config))
    WORKDIR=CONFIG["workdir"]
    TAG=args.tag


    client=DockSing.connect(SSH)
    client.setup(WORKDIR)
    client.push(TAG,WORKDIR)
    client.build(TAG,WORKDIR)
    client.submit(TAG,WORKDIR,CONFIG)
        
    

    
