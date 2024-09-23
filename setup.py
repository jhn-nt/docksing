from setuptools import setup

setup(
    name="docksing",
    version="0.2.18",
    description="Lightweight Docker to Singularity to HPC Deployer",
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