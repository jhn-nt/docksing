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
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import List
import warnings
import time
import cmd


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
        # overriding key bindings
        for key,item in override.items():
            if key in data:
                data[key]=item
            else:
                raise ValueError(f"{key} not found in data.")

        # ignoring key bindings
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
            elif key=="entrypoint":
                cmd+=[f"--entrypoint {item}"]
            else:
                raise ValueError(f"{key} not supported.")
        return cmd

    @staticmethod
    def singularity_run_opt(data:dict,override:dict={},ignore:list=[])->List[str]:
        # overriding key bindings
        for key,item in override.items():
            if key in data:
                data[key]=item
            else:
                raise ValueError(f"{key} not found in data.")

        # ignoring key bindings
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
                cmd+=[f"--bind {vol}" for vol in item]
            elif key=="ports":
                cmd+=[f"-p {p}" for p in item]
            elif key=="image":
                pass
            elif key=="commands":
                pass
            elif key=="entrypoint":
                cmd+=[f"--entrypoint {item}"]
            elif key=="working_dir":
                cmd+=[f"--pwd {item}"]
            else:
                raise ValueError(f"{key} not supported.")
        return cmd
    
    @staticmethod
    def slurm_run_opt(data:dict)->List[str]:
        cmd=["srun"]
        for key, item in data.items():
            cmd+=[f"--{key}={item}"]
        return cmd
            
    @staticmethod
    def singularity_build_opt(iid:str,remotedir:str)->List[str]:
        cmd=["singularity build",f"{remotedir}/{iid}.sif",f"docker-archive://{remotedir}/{iid}.tar"]
        return cmd

@dataclass
class DockSing:
    ssh: SSHClient=field(repr=False)
    docker: DockerClient=field(repr=False)

    @classmethod
    def connect(cls,ssh:str)->DockSing:
        """Instantiate a `Docksing` object by establishing a connection to the remote host via an `ssh` connection string and local docker daemon.

        Args:
            ssh (str): Connetion string in the form `username@hostname`

        Returns:
            DockSing: An instance of `DockSing` capable of communicating with the remote host and the local docker daemon.
        """
        username,hostname=ssh.rsplit("@",1)

        ssh_client=SSHClient()
        ssh_client.set_missing_host_key_policy(AutoAddPolicy())
        ssh_client.connect(hostname=hostname,username=username,password=getpass(f"Password for {ssh}:"))

        return cls(ssh=ssh_client,docker=docker.from_env())
    
    @classmethod
    def local(cls)->DockSing:
        """Instantiate a `Docksing` object by establishing a connection to the local docker daemon.

        Returns:
            DockSing: An instance of `DockSing` capable of communicating with the local docker daemon.
        """
        return cls(ssh=None,docker=docker.from_env())
    
    def setup(self,remotedir:str):
        """Asserts whether the folder `remotedir` exists in the remote host (or in the current working directory if in local mode), if it does not, it creates it.
        By design, `Docsking.setup` will raise an error if `remotedir` already exists.
        This behavior is intended to prevent accidental overwriting of valuable data. 

        Args:
            remotedir (str): Absolute path of working directory on the remote host.
        """
        if self.ssh:
            sftp=SFTPClient.from_transport(self.ssh.get_transport())
            if remotedir in sftp.listdir():
                raise ValueError(f"remotedir:{remotedir} already exists in the remote host, consider changing the remotedir.")
            else:
                sftp.mkdir(remotedir)
        else:
            if Path(remotedir).is_dir():
                raise ValueError(f"remotedir:{remotedir} already exists in the local hor host, consider changing the remotedir.")
            else:
                _=os.mkdir(Path.cwd() / remotedir)

    def push(self,tag:str,remotedir:str):
        """Pushes the target oci image `tag` from the local docker daemon to the remote host as a `.tar` archive file in `remotedir`.
        

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
    
    def map_remote_volume(self,remote_dir:str,local_dir:str,container_dir:str,send_payload:bool=False)->str:
        """Given a volume mapping in the form of `local_dir:container_dir` and a target `remote_dir`,
        `Docksing.map_remote_volume` first copies over SSH SCP the content of `local_dir` into `remote_dir/local_dir`
        then updates the volume mapping to be run remotely accordingly as `remote_dir/local_dir:container_dir`.

        Args:
            remote_dir (str): Remote direcorty as indicated in `remote_dir`
            local_dir (str): The local directory of the volume mapping.
            container_dir (str): The container direcotry of the volume mapping.

        Returns:
            str: The updated singularity volume mapping in the form `remote_dir/local_dir:container_dir`.
        """
        if local_dir==remote_dir:
            # If the mapping points to the remote dir, then remote_dir is already a valid target path
            warnings.warn(f"It is advisable to map subdirectories of remotedir, not remotedir directly,Found:{remote_dir}")
            remote_map=remote_dir
        else:
            # Otherwise, we need to prepend the remot_dir path to the local_dir leaf to properly build the remote target path
            remote_map=f"{remote_dir}/{Path(local_dir).name}"

        if self.ssh:
            if send_payload and Path(local_dir).is_dir():
                # If the mapping points to an existing local folder,
                # we copy its content in remote_dir/local_host
                with SCPClient(self.ssh.get_transport()) as scp:
                    scp.put(
                        local_dir,
                        remote_path=remote_dir,
                        recursive=True)
                
        
            if local_dir!=remote_dir:
                # If local_dir, the source bind, does not exists locally, there is no data to be copied over SSH SCP.
                # In docker, the source bind would then be generated by default.
                # In singularity, however, an error is raised if the source bind does not exist.
                # To maintain the highest alignment to docker behavior, we then assert the existence of source bind, 
                # and if it does not exists, we generate the folder before sending running singularity in order to circumvent the error.
                sftp=SFTPClient.from_transport(self.ssh.get_transport())
                if send_payload and Path(local_dir).name not in sftp.listdir(path=remote_dir):
                    # Checking if remote_dir/local_dir already exists in remote and creates it if it does not.
                    # TODO: this functionality should be moved to setup
                    sftp.mkdir(remote_map)



        return f"{remote_map}:{container_dir}"

    def override_volumes(self,remote_dir:str,container_config:dict,send_payload:bool=False)->dict:
        """Given a `container_config` file, this methods searches if a volume mapping is requested, 
        if it does and `send_payload` is set to `True`, it starts and SCP transfer in order to copy the content of `container_config['volumes']` to `remote_dir`.
        
        Args:
            remote_dir (str): The remote directory where to store the volumes.
            container_config (dict): A dictionare container the docker configuration data.
            send_payload (bool, optional): Boolean indicating the initiation of file transfer from local to remote. Defaults to False.

        Returns:
            dict: A symbolic volume mapping to eventually pass to singularity. Returns an empty dictionary if no volumes are requested in `container_config`.
        """

        if "volumes" in container_config:
            remote_volumes=[]
            pbar=tqdm(container_config["volumes"],total=len(container_config["volumes"]),disable=send_payload)
            for volume in pbar:
                local_dir,container_dir=volume.split(":")
                remote_volumes.append(self.map_remote_volume(remote_dir,local_dir,container_dir,send_payload=send_payload))
            return {"volumes":remote_volumes}
        else:
            return {}

    def submit(self,tag:str,remotedir:str,container_config:List[str],slurm_config:List[str],attach:bool=False):
        """Submits the containerized job as defined in `config.yaml` to the remote host.
        `Docksing.submit` is the core of `Docksing`, as it is responsible of parsing the `config.yaml` file thorugh the `CLICompose` utility, copyng evantual data from local to remote,
        and then intiiate jobs, either remotely or locally.
        If `Docksing` is instantiated via `Docksing.connect`, thus is able of directly connecting to remote host, it then starts a slurm job remotely.
        If `Docksing` is instantiated via `Docksing.local`, thus is not able of directly connecting to remote host, it then starts a local container to run the job.

        Args:
            tag (str): Name of the target image tag.
            remotedir (str): Absolute path of working directory on the remote host.
            container_config (List[str]): A dictionary built from the `container` chapter in the `config.yaml`
            slurm_config (List[str]): A dictionary built from the `slurm` chapter in the `config.yaml`
            attach (bool, optional): If set to True makes `Docksing.submit` a blocking function.
        """
        if self.ssh:
            image=self.docker.images.get(tag)
            iid=image.short_id.split(":")[1]

            
            slurm_cmd=CLICompose.slurm_run_opt(slurm_config)
            build_cmd=CLICompose.singularity_build_opt(iid,remotedir)
            run_cmd=CLICompose.singularity_run_opt(container_config,
                                                   override={"image":f"{remotedir}/{iid}.sif",**self.override_volumes(remotedir,container_config,send_payload=True)},
                                                   ignore=["container_name"])
            opt_cmd=CLICompose.container_opt(container_config)

            inner_cmd=" ".join(build_cmd+["&&"]+run_cmd+opt_cmd)
            cmd=" ".join(slurm_cmd)+f" bash -c \"{inner_cmd}\""

            if attach:
                # if requested, stream ssh output to local console
                self.ssh.exec_command(f"{cmd}")
            else:
                # otherwise stream output to remote stdout.txt
                self.ssh.exec_command(f"nohup {cmd} > {remotedir}/stdout.txt 2>&1 &")
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
                
    def cli(self,remotedir:str,tag:str,container_config:List[str],slurm_config:List[str],local:bool)->str:
        """Non-functional twin method of `Docksing.submit` which only prints out the CLI string of the job submiossion command without executing it.
        It can be useful for debugging purposes.

        Args:
            tag (str): Name of the target image tag.
            remotedir (str): Absolute path of working directory on the remote host.
            container_config (List[str]): A dictionary built from the `container` chapter in the `config.yaml`
            slurm_config (List[str]): A dictionary built from the `slurm` chapter in the `config.yaml`
            local (bool): Flag indicating if the job was requested locally or remotely.

        Returns:
            str: CLI command.
        """
        if not local:
            image=self.docker.images.get(tag)
            iid=image.short_id.split(":")[1]

            slurm_cmd=CLICompose.slurm_run_opt(slurm_config)
            build_cmd=CLICompose.singularity_build_opt(iid,remotedir)
            run_cmd=CLICompose.singularity_run_opt(container_config,
                                                   override={"image":f"{remotedir}/{iid}.sif",**self.override_volumes(remotedir,container_config,send_payload=False)},
                                                   ignore=["container_name"])
            opt_cmd=CLICompose.container_opt(container_config)

            inner_cmd=" ".join(build_cmd+["&&"]+run_cmd+opt_cmd)
            cmd=" ".join(slurm_cmd)+f" bash -c \"{inner_cmd}\""
        else:
            cmd=CLICompose.docker_run_opt(container_config)+CLICompose.container_opt(container_config)
            cmd=" ".join(cmd)
        
        return cmd
    
    def stream_stdout_from_config(self,remotedir:str):
        """Redirects the remote `stdout` and `stderr` to the local console.

        Args:
            remotedir (str): Absolute path of working directory on the remote host.
        """
        stdin, stdout, stderr=self.ssh.exec_command(f"tail -f {remotedir}/stdout.txt")
        stdout.channel.set_combine_stderr(True)
        
        while True:
            if stdout.channel.recv_ready():
                print(stdout.readline())
            time.sleep(.1)



def main():
    from argparse import ArgumentParser
    import yaml


    parser=ArgumentParser()

    parser.add_argument("--ssh",action="store",required=True)
    parser.add_argument("--config",action="store",required=True)
    parser.add_argument("--local",action="store_true")
    parser.add_argument("--cli",action="store_true")
    parser.add_argument("--attach",action="store_true")
    parser.add_argument("--stream",action="store_true")
    parser.add_argument("--kill",action="store_true") #TODO



    args,other=parser.parse_known_args()

    SSH=args.ssh
    CONFIG=yaml.safe_load(open(args.config))
    LOCAL=args.local
    CLI=args.cli
    ATTACH=args.attach
    STREAM=args.stream
    

    if LOCAL:
        client=DockSing.local()
    elif CLI:
        client=DockSing.local()
    else:
        client=DockSing.connect(SSH)

    if CLI:
        print(client.cli(CONFIG["remotedir"],CONFIG["container"]["image"],CONFIG["container"],CONFIG["slurm"],LOCAL))
    elif STREAM:
        client.stream_stdout_from_config(CONFIG["remotedir"])
    else:
        client.setup(CONFIG["remotedir"])
        client.push(CONFIG["container"]["image"],CONFIG["remotedir"])
        client.submit(CONFIG["container"]["image"],CONFIG["remotedir"],CONFIG["container"],CONFIG["slurm"],attach=ATTACH)

    

if __name__=="__main__":
    main()

        
    

    
