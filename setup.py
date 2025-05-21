from setuptools import setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="docksing",
    version="0.2.30",
    description="CLI Utility for deployment of containerized jobs on SLURM HPC ",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="G. Angelotti",
    author_email="giovanni.angelotti@idsia.ch",
    py_modules=["docksing"],
    install_requires=[
        "paramiko==3.4.0",
        "scp==0.15.0",
        "docker==7.1.0",
        "tqdm==4.66.4"
    ],
    entry_points={"console_scripts":["docksing=docksing:main"]}
)
