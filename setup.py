#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

with open("README.md") as readme_file:
    readme = readme_file.read()

requirements = ["tamarco==0.*", "aioamqp==0.13.0"]

setup(
    name="tamarco-amqp",
    version="0.1.0",
    description="AMQP resource for Tamarco microservice framework.",
    long_description=readme,
    long_description_content_type="text/markdown",
    author="System73 Engineering Team",
    author_email="opensource@system73.com",
    url="https://github.com/System73/tamarco-amqp",
    packages=["tamarco_amqp"],
    include_package_data=True,
    install_requires=requirements,
    zip_safe=False,
    keywords=["tamarco", "amqp", "microservices"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Programming Language :: Python :: 3.6",
    ],
    test_suite="pytests",
)
