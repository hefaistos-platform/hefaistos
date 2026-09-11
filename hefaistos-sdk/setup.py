from setuptools import setup, find_packages

setup(
    name="hefaistos-sdk",
    version="1.0.0",
    description="SDK for building HEFAISTOS connectors",
    author="HEFAISTOS Team",
    packages=find_packages(), # Automatically find the 'hefaistos_sdk' package
    install_requires=[
        "pika",
        "requests"
    ],
    python_requires=">=3.11",
)
