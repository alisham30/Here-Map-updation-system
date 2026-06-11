"""Setup script for baseline ingestion package."""

from setuptools import setup, find_packages

setup(
    name="place-change-detection-baseline-ingestion",
    version="1.0.0",
    description="Baseline data ingestion and normalization for place-change detection system",
    author="Geospatial Data Engineering Team",
    python_requires=">=3.8",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "pandas>=2.0.0",
        "geopandas>=0.12.0",
        "pyarrow>=12.0.0",
        "shapely>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "baseline-ingest=pipeline.ingestion_pipeline:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
