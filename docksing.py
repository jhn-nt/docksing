from __future__ import annotations
from dataclasses import dataclass, field
from paramiko import SSHClient, AutoAddPolicy, SFTPClient
from scp import SCPClient
import docker
from tqdm import tqdm
from docker.client import DockerClient
from getpass import getpass
from functools import partial
import io
import subprocess
import os
from pathlib import Path
from typing import List
import warnings


@dataclass
class CLICompose:

    @staticmethod
    def container_opt(data:dict)->List[str]:
        REQUIRED=["image"]
        assert set(REQUIRED).issubset(data.keys()), f"Missing mandatory bindings: {set(REQUIRED).difference(data.keys())}"

        cmd=[data["image"]]
        if "commands" in data.keys():
            assert isinstance(data["commands"],list)
            cmd+=[" ".join(data["commands"])]
        return cmd

    @staticmethod
    def docker_run_opt(data:dict,override:dict={},ignore:list=[])->List[str]:
        data= data | override
        data={key:item for (key,item) in data.items() if key not in ignore}

        cmd=["docker run"]
        for key, item in data.items():
            if key=="environment":
                if isinstance(item,list):
                    temp={}
                    [temp:=temp|d for d in item]
                    item=temp

                cmd+=[f"--env {k}={v}" for (k,v) in item.items()]
            elif key=="volumes":
                cmd+=[f"--volume {vol}" for vol in item]
            elif key=="ports":
                cmd+=[f"-p {p}" for p in item]
            elif key=="image":
                pass
            elif key=="commands":
                pass
            elif key=="working_dir":
                cmd+=[f"--workdir {item}"]
            elif key=="container_name":
                cmd+=[f"--name {item}"]
            else:
                raise ValueError(f"{key} not supported.")
        return cmd

    @staticmethod
    def singularity_run_opt(data:dict,override:dict={},ignore:list=[])->List[str]:
        data= data | override
        data={key:item for (key,item) in data.items() if key not in ignore}

        cmd=["singularity run"]
        for key, item in data.items():
            if key=="environment":
                if isinstance(item,list):
                    temp={}
                    [temp:=temp|d for d in item]
                    item=temp

                    cmd+=[f"--env {k}={v}" for (k,v) in item.items()]
            elif key=="volumes":
                warnings.warn("Consider passing data thorugh APIs instead of volumes.")
                cmd+=[f"--volume {vol}" for vol in item]
            elif key=="ports":
                cmd+=[f"-p {p}" for p in item]
            elif key=="image":
                pass
            elif key=="commands":
                pass
            elif key=="working_dir":
                cmd+=[f"--workdir {item}"]
            else:
                raise ValueError(f"{key} not supported.")
        return cmd
    
    @staticmethod
    def slurm_run_opt(data:dict)->List[str]:
        cmd=["srun"]
        for key, item in data.items():
            cmd+=[f"--{key}={item}"]
        return cmd
            

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
    
    @classmethod
    def local(cls)->DockSing:
        return cls(ssh=None,docker=docker.from_env())
    
    def setup(self,remotedir:str):
        """Asserts whether `remotedir` exists in remote host and otherwise creates it.

        Args:
            remotedir (str): Absolute path of working directory on host.
        """
        if self.ssh:
            sftp=SFTPClient.from_transport(self.ssh.get_transport())
            sftp.mkdir(remotedir)
        else:
            _=os.mkdir(Path.cwd() / remotedir)

    def push(self,tag:str,remotedir:str):
        """Pushes the target oci image `image` from the local docker daemon to the remote host as a `.tar` archive file in `remotedir`.

        Args:
            tag (str): Name of the target image tag.
            remotedir (str): Absolute path of working directory on host.
        """
        
        image=self.docker.images.get(tag)
        iid=image.short_id.split(":")[1]
        with io.BytesIO() as file:
            for blob in image.save():
                file.write(blob)
            file.seek(0)

            if self.ssh:
                with SCPClient(self.ssh.get_transport()) as scp:
                    scp.putfo(file,f"{remotedir}/{iid}.tar")
            else:
                with open(f"{remotedir}/{iid}.tar","wb") as f:
                    f.write(file.getbuffer())
    
    def remote_volume(self,remote_dir:str,local_dir:str,container_dir:str,send_payload:bool=False)->str:
        """If a volume mount of the form `local_dir:container_dir` is requested then `docksing` sends the content of `local_dir` via
        scp to `remote_dir/local_dir` and submits to singularity the mapping `remote_dir/local_dir:conatainer_dir`.

        Args:
            remote_dir (str): Remote direcorty as indicited in `remote_dir`
            local_dir (str): The local directory of the volume mapping.
            container_dir (str): The container direcotry of the volume mapping.

        Returns:
            str: The updated singularity mapping.
        """
        if send_payload:
            with SCPClient(self.ssh.get_transport()) as scp:
                scp.put(
                    local_dir,
                    remote_path=remote_dir,
                    recursive=True)
        
        return f"{remote_dir}{local_dir}:{container_dir}"

    def override_volumes(self,remote_dir:str,container_config:dict,send_payload:bool=False)->dict:
        """Given a `container_config` file, this methods searches if a volume mapping is requested, 
        if it does and `send_payload` is set to `True`, it starts and SCP transfer to `remote_dir`.
        
        Args:
            remote_dir (str): The remote directory where to store the volumes.
            container_config (dict): A dictionare container the docker configuration data.
            send_payload (bool, optional): Boolean indicating the initiation of file transfer from local to remote. Defaults to False.

        Returns:
            dict: A symbolic volume mapping to eventually pass to singularity. Returns an empty dictionary if no volumes are requested in `container_config`.
        """

        if "volumes" in container_config:
            remote_volumes=[]
            pbar=tqdm(container_config["volumes"],total=len(container_config["volumes"]))
            for volume in pbar:
                local_dir,container_dir=volume.split(":")
                remote_volumes.append(self.remote_volume(remote_dir,local_dir,container_dir,send_payload=send_payload))
            return {"volumes":remote_volumes}
        else:
            return {}

    def build(self,tag:str,remotedir:str):
        """Generates a `.sif` file from a docker image archive file.

        Args:
            image (str): Name of the target image tag.
            remotedir (str): Absolute path of working directory on host.
        """
        if self.ssh:
            image=self.docker.images.get(tag)
            iid=image.short_id.split(":")[1]
            self.ssh.exec_command(f"cd {remotedir}; srun singularity build {iid}.sif docker-archive://{iid}.tar")

    def submit(self,tag:str,remotedir:str,container_config:List[str],slurm_config:List[str]):
        if self.ssh:
            image=self.docker.images.get(tag)
            iid=image.short_id.split(":")[1]

            slurm_cmd=CLICompose.slurm_run_opt(slurm_config)
            run_cmd=CLICompose.singularity_run_opt(container_config,
                                                   override={"image":f"{iid}.sif"} | self.override_volumes(remotedir,container_config,send_payload=True),
                                                   ignore=["container_name"])
            opt_cmd=CLICompose.container_opt(container_config)
            cmd=" ".join(slurm_cmd+run_cmd+opt_cmd)
            self.ssh.exec_command(f"cd {remotedir}; nohup {cmd} 2>&1 | tee stdout.txt &")
        else:
            run_cmd=CLICompose.docker_run_opt(container_config)
            opt_cmd=CLICompose.container_opt(container_config)
            cmd=" ".join(run_cmd+opt_cmd)

            with open(Path.cwd() / remotedir / "stdout.txt","w") as log:
                _=subprocess.Popen(cmd,
                                   cwd=Path.cwd() / remotedir,
                                   shell=True,
                                   stdout=log,
                                   stderr=subprocess.STDOUT,
                                   start_new_session=True)
                
    def cli(self,remotedir:str,tag:str,container_config:List[str],slurm_config:List[str]):
        if self.ssh:
            image=self.docker.images.get(tag)
            iid=image.short_id.split(":")[1]
            slurm_cmd=CLICompose.slurm_run_opt(slurm_config)
            run_cmd=CLICompose.singularity_run_opt(container_config,
                                                   override={"image":f"{iid}.sif"} | self.override_volumes(remotedir,container_config,send_payload=False),
                                                   ignore=["container_name"])
            opt_cmd=CLICompose.container_opt(container_config)
            cmd=" ".join(slurm_cmd+run_cmd+opt_cmd)
        else:
            cmd=CLICompose.docker_run_opt(container_config)+CLICompose.container_opt(container_config)
            cmd=" ".join(cmd)
        
        return cmd

        

        


        

if __name__=="__main__":
    from argparse import ArgumentParser
    import yaml


    parser=ArgumentParser()

    parser.add_argument("--ssh",action="store",required=True)
    parser.add_argument("--config",action="store",required=True)
    parser.add_argument("--local",action="store_true")
    parser.add_argument("--cli",action="store_true")



    args,other=parser.parse_known_args()

    SSH=args.ssh
    CONFIG=yaml.safe_load(open(args.config))
    LOCAL=args.local
    CLI=args.cli
    

    if LOCAL:
        client=DockSing.local()
    else:
        client=DockSing.connect(SSH)

    if CLI:
        print(client.cli(CONFIG["remotedir"],CONFIG["container"]["image"],CONFIG["container"],CONFIG["slurm"]))
    else:
        client.setup(CONFIG["remotedir"])
        client.push(CONFIG["container"]["image"],CONFIG["remotedir"])
        client.build(CONFIG["container"]["image"],CONFIG["remotedir"])
        client.submit(CONFIG["container"]["image"],CONFIG["remotedir"],CONFIG["container"],CONFIG["slurm"])
        
    

    
