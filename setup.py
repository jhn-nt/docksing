from setuptools import setup

setup(
    name="docksing",
    version="0.2.21",
    description="CLI Utility for deployment of containerized jobs on SLURM HPC ",
    author="G. Angelotti",
    author_email="giovanni.angelotti@idsia.ch",
    py_modules=["docksing"],
    install_requires=[
        "paramiko==3.4.0",
        "scp==0.15.0",
        "docker==7.1.0",
        "tqdm==4.66.4"
    ]
    
)