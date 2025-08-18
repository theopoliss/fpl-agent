#!/usr/bin/env python3
"""
Script to switch to simple models for Python 3.13 compatibility
"""
import os
import shutil

# Backup original models.py
if os.path.exists('src/data/models.py'):
    shutil.copy('src/data/models.py', 'src/data/models_pydantic.py')
    print("✓ Backed up original models.py to models_pydantic.py")

# Replace with simple models
if os.path.exists('src/data/models_simple.py'):
    shutil.copy('src/data/models_simple.py', 'src/data/models.py')
    print("✓ Replaced models.py with simple version")
    
print("\nNow you can use the FPL agent without pydantic!")
print("Run: python quick_test.py")