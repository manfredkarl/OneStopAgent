#!/bin/bash
set -e

# Python API dependencies
cd src/python-api
pip install -r requirements.txt
npm install  # PptxGenJS

# Frontend dependencies
cd ../frontend
npm install

echo "Setup complete!"
