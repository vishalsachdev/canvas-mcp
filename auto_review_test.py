#!/usr/bin/env python3
"""
Test file to verify automatic Claude review functionality.

This file contains intentional issues to test Claude's review capabilities:
- Missing error handling
- No type hints
- Potential security issue
- Performance concern
"""

import os
import subprocess

def process_user_input(user_input):
    # Security issue: no input validation
    command = f"echo {user_input}"
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.stdout

def read_file(filename):
    # Missing error handling
    with open(filename, 'r') as f:
        return f.read()

def inefficient_search(data, target):
    # Performance issue: O(n²) when O(n) would work
    matches = []
    for i in range(len(data)):
        for j in range(len(data)):
            if data[i] == target:
                matches.append(i)
    return matches

class DataProcessor:
    def __init__(self):
        self.data = []
    
    def add_item(self, item):
        # No type hints
        self.data.append(item)
    
    def process(self):
        # No documentation
        return [x * 2 for x in self.data if x > 0]

if __name__ == "__main__":
    processor = DataProcessor()
    processor.add_item(5)
    print(processor.process())