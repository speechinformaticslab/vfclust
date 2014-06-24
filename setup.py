import os
import subprocess
from distutils.core import setup
from distutils.command.install import install as distutils_install

from pip.req import parse_requirements


basedir = os.path.dirname(__file__)
requirements_path = os.path.join(basedir, 'requirements.txt')

# parse_requirements() returns generator of pip.req.InstallRequirement objects
install_requirements = parse_requirements(requirements_path)

# Convert to setup's list of strings format:
requirements = [str(ir.req) for ir in install_requirements]


# executes makefile and then installs
class MyInstall(distutils_install):
    def run(self):
        try:
            subprocess.call(['make'])
        except Exception as e:
            print e
            print "Error compiling t2p.c.   Try running 'make'."
            exit(1)
        else:
            distutils_install.run(self)

setup(
    name='VFClust',
    version='0.1.1',
    packages=['vfclust'],
    py_modules=['vfclust'],
    include_package_data=True,
    url='https://github.umn.edu/speechinformaticslab/vfclust/',  # TODO: Make a public URL
    license='Apache License, Version 2.0',
    author='Thomas Christie, James Ryan, and Serguei Pakhomov',
    author_email='tchristie@umn.edu',
    description="Clustering of Verbal Fluency responses.",
    long_description=open('README.rst').read(),
    # install_requires=requirements,  # TODO: Add in after making app.py work again.
    cmdclass={'install': MyInstall},
    entry_points={
        'console_scripts': [
            'vfclust = vfclust.vfclust:main',
        ],
    },
    classifiers=[
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: Healthcare Industry",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Natural Language :: English",
        "Programming Language :: C",
        "Topic :: Multimedia :: Sound/Audio :: Speech",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "Topic :: Software Development :: Libraries",
        "Topic :: Text Processing :: Linguistic"
    ]
)


