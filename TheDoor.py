#/bin/python
# -*- coding: utf-8 -*-

import argparse
import calendar
import csv
import glob
import hashlib
import html
import importlib
import itertools
import os
import platform
import queue
import random
import re
import requests
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
import urllib.request
from urllib.error import HTTPError, URLError
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from io import StringIO

# List of User-Agent strings
user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

# List of required third-party modules
third_party_modules = [
    'chardet',
    'pygame',
    'bs4',  # BeautifulSoup (part of bs4 package)
    'tqdm',
    'PySimpleGUI',
    'colorama',
]

def check_and_install_modules():
    os_name = platform.system()

    if os_name == "Linux":
        # Install pip if not already installed
        try:
            subprocess.check_call(["sudo", "apt", "-qq", "-y", "install", "python3-pip"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("Failed to install pip. Ensure you have sudo privileges.")

        # Install python3-tk
        try:
            subprocess.check_call(["sudo", "apt", "-qq", "-y", "install", "python3-tk"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("Failed to install python3-tk. Ensure you have sudo privileges.")

    elif os_name == "Darwin":  # macOS
        # Check if Tkinter is available
        try:
            import tkinter
            print("Tkinter is available.")
        except ImportError:
            print("Tkinter is not available. Please install it manually or ensure your Python installation includes Tkinter.")
            # Optionally, you could guide users to install Python with Tkinter:
            print("You might need to reinstall Python with Tkinter support. For example, using Homebrew:")
            print("brew install python --with-tcl-tk")

    # For Windows, we'll rely on pip for Python packages
    # Note: System packages like tkinter should be pre-installed or installed manually

    for module in third_party_modules:
        try:
            importlib.import_module(module)
            print(f"{module} is already installed.")
        except ImportError:
            print(f"{module} is not installed.")
            pip_command = [sys.executable, '-m', 'pip', 'install', module]
            try:
                subprocess.check_call(pip_command)
                print(f"{module} installed successfully.")
            except subprocess.CalledProcessError:
                print(f"Failed to install {module}.")

def import_modules():
    # Your existing import logic here
    global chardet, concurrent, pygame, BeautifulSoup, Pool, tqdm, stop_flag, sg
    import chardet
    import concurrent.futures
    import pygame
    from bs4 import BeautifulSoup
    from multiprocessing import Pool
    from tqdm import tqdm
    import PySimpleGUI as sg
    stop_flag = threading.Event()
    from colorama import Fore, Style, init

# Function to get a random User-Agent
def get_random_user_agent():
    return random.choice(user_agents)

# Define global variables and directories
failed_downloads = []
verbose = "-v" in sys.argv
edgar_url = "https://www.sec.gov/Archives/edgar/data/"
headers = {'User-Agent': "anonymous/FORTHELULZ@anonyops.com"}
backup_headers = {"User-Agent": "anonymost/FORTEHLULZ@anonops.com"}
files_found_count = 0
done = False
download_directory = os.path.join(os.path.expanduser("~"), "sec_archives")
download_directory2 = os.path.join(os.path.expanduser("~"), "edgar")
base_path = (download_directory2)
os.makedirs(download_directory, exist_ok=True)
os.makedirs(download_directory2, exist_ok=True)

# Create a list of all subdirectories from 1993 to 2024, including all four quarters
years = range(1993, 2025)
quarters = ["QTR1", "QTR2", "QTR3", "QTR4"]
base_url = "https://www.sec.gov/Archives/edgar/full-index"

subdirectories = [
    f"{base_url}/{year}/{quarter}/master.zip"
    for year in years
    for quarter in quarters
    if not (year == 2024 and quarter in ["QTR3", "QTR4"])
]
processes = []

# URLs of the files to download
urls = [
    "https://raw.githubusercontent.com/ngshya/pfsm/master/data/sec_edgar_company_info.csv",
    "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"
]

# Define the desired filenames
file_names = ["edgar_CIKs.csv", "edgar_CIK2.csv"]

# Function to check free space
def check_free_space():

    total_size = sum(os.path.getsize(os.path.join(download_directory, f)) for f in os.listdir(download_directory) if f.endswith('.zip'))
    free_space = shutil.disk_usage(download_directory).free
    print(f"Total size needed: {total_size} bytes, Free space available: {free_space} bytes")
    return free_space > total_size

def download_pre_files():
    log_filename = os.path.join(download_directory, 'archives.log')
    downloaded_files = {}  # Changed to dict for file_name to hash mapping
    if os.path.exists(log_filename):
        with open(log_filename, 'r') as log:
            for line in log:
                parts = line.strip().split(',')
                if len(parts) > 3:  # Expecting timestamp, subdirectory, file_size, md5_hash
                    downloaded_files[parts[2]] = parts[3]  # file_name, md5_hash

    with open(log_filename, 'a') as log_file:
        for subdirectory in tqdm(subdirectories, desc="Downloading Archives"):
            # Extract the directory and subdirectory name from the URL
            path_parts = subdirectory.split('/')
            year = path_parts[-3]
            quarter = path_parts[-2]
            subdirectory_name = f"{year}_{quarter}"
            filename = os.path.join(download_directory, f"{subdirectory_name}.zip")
            
            if filename in downloaded_files:
                continue

            retries = 3
            delay = 1

            # Ensure the download directory exists
            os.makedirs(download_directory, exist_ok=True)

            for attempt in range(retries):
                try:
                    headers = {'User-Agent': "anonymous/FORTHELULZ@anonyops.com"}

                    # Create a request object with headers
                    req = urllib.request.Request(subdirectory, headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as response:
                        content = response.read()
                        file_size = len(content)
                        md5_hash = hashlib.md5(content).hexdigest()
                        
                        # Write the content to file
                        with open(filename, 'wb') as file:
                            file.write(content)
                                                
                        # Log the download with timestamp, file name, size, and hash
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        log_file.write(f"{timestamp},{subdirectory},{filename},{file_size},{md5_hash}\n")
                        log_file.flush()  # Ensure the write is immediate

                    break  # Exit the retry loop if successful

                except (urllib.error.HTTPError, urllib.error.URLError) as e:
                    print(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < retries - 1:
                        time.sleep(delay * (2 ** attempt))
            else:
                print(f"Failed to download {subdirectory} after {retries} retries")
                failed_downloads.append(subdirectory)

    return failed_downloads

def download_daily_index_files():
    base_url = "https://www.sec.gov/Archives/edgar/daily-index/"
    today = datetime.now()
    end_date = today - timedelta(days=1)
    daily_index_log = "./sec_archives/daily-index-log.txt"
    #downloaded_files = set()
    downloaded_files = {}
    
    # Read existing log to check for downloaded files
    if os.path.exists(daily_index_log) and os.path.getsize(daily_index_log) > 0:
        try:
            with open(daily_index_log, 'r') as log:
                for line in log:
                    parts = line.strip().split(',')
                    if len(parts) == 4:
                        downloaded_files[parts[1]] = parts[3]
                    else:
                        print(f"Warning: Malformed log entry: {line.strip()}")
        except IOError as e:
            print(f"Error reading log file: {e}")
    else:
        print("Log file is empty or does not exist.")

    # Determine current quarter and year
    current_year = end_date.year
    current_quarter = (end_date.month - 1) // 3 + 1
    
    # Set start date for the current quarter
    start_date = datetime(current_year, (current_quarter - 1) * 3 + 1, 1)
    
    # Define the directory path where the zip file will be stored
    zip_directory = "./sec_archives/"
    
    # Check if the directory exists, if not, create it
    if not os.path.exists(zip_directory):
        os.makedirs(zip_directory)
    
    zip_path = f"{zip_directory}{current_year}-QTR{current_quarter}.zip"
    master_idx_file = "2024-QTR3.idx"  # Name for the master index file

    # List of dates to skip
    skip_dates = [datetime(2024, 7, 3), datetime(2024, 7, 4), datetime(2024, 9, 2)]

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        master_idx_content = []
        current_date = max(start_date, datetime(2024, 7, 1))
        total_days = (end_date - current_date).days + 1
        pbar = tqdm(total=total_days, desc="Downloading", unit="files")

        while current_date <= end_date:
            if current_date.weekday() >= 5 or current_date in skip_dates:
                current_date += timedelta(days=1)
                pbar.update(1)
                continue
            
            file_name = f"master.{current_date.strftime('%Y%m%d')}.idx"
            if file_name in downloaded_files:
                current_date += timedelta(days=1)
                pbar.update(1)
                continue

            url = f"{base_url}{current_date.year}/QTR{(current_date.month-1)//3+1}/{file_name}"
            max_attempts = 3
            print(f"Attempting to download {url}")
            for attempt in range(max_attempts):
                try:
                    headers = {'User-Agent': "FORTHELULZ@anonops.com"}
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=3) as response:
                        if response.getcode() == 200:
                            content = response.read()
                            file_size = len(content)
                            file_hash = hashlib.sha256(content).hexdigest()
                            print(f"Successfully downloaded {file_name}. Size: {file_size} bytes. Hash: {file_hash}")

                            # Decode content here to avoid reading twice
                            idx_content = content.decode('utf-8').split('\n')
                            if not master_idx_content:
                                print("Setting up master index header.")
                                master_idx_content = idx_content[:11]
                            master_idx_content.extend(idx_content[11:])

                            # Log the download
                            with open(daily_index_log, 'a') as log:
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                log.write(f"{timestamp},{file_name},{file_size},{file_hash}\n")
                            print(f"Logged download of {file_name}")
                            break
                        else:
                            print(f"Failed to download {file_name}. Status: {response.getcode()}")
                except (urllib.error.HTTPError, urllib.error.URLError) as e:
                    print(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < max_attempts - 1:
                        time.sleep(1)  # Delay before retry
                    else:
                        print(f"Max attempts reached for {file_name}. Moving on.")

            current_date += timedelta(days=1)
            pbar.update(1)

        # Write the master index content to the zip file
        if master_idx_content:
            print("Writing master index to ZIP file...")
            zipf.writestr(master_idx_file, '\n'.join(master_idx_content))
            print(f"Master index file {master_idx_file} written to {zip_path}")

    pbar.close()
    print(f"\nDaily index files up to {end_date.strftime('%Y-%m-%d')} have been processed and saved to {zip_path}.")

# Function to clear the terminal screen
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# Function to generate a random color
def random_color():
    return f"\033[38;5;{random.randint(0, 255)}m"

# Function to reset color
def reset_color():
    return "\033[0m"

# Function to display Pacman moving across the screen
def display_power():
    power_frames = [
	"""                                                                 
                            bbbbbbbbb                            
                          bbdb     dbdb                          
                          bd  dbdbd  bb                          
                          bb bb   bb db                          
                    bbbbd bd bd   bd bb dbbbb                    
                 bbdbd bb bb bb   bb bd bb dbdbb                 
               bbdb    bd bd bd   db bb bd    bdbb               
             bbdb     bdb bb bb   bb db dbb     dbdb             
            bdb    bbdbb  db db   bd bd  bbbdb    bbd            
           bbb    bdb     bb bdbdbbb bb     bbb    bbd           
         bbd    bdb       bdbb     dbdb       dbb    bbb         
         bd     bb          bdbbbdbbb          bd     db         
        bdb    dbd                             bbb    bdb        
        bb     bb                               db     bb        
        bd     bd                               bd     db        
        bb     bbb                             bdb     bd        
        dbb     db                             bb     bbb        
         bd     bbd                           dbd     db         
          bbb     bbb                       bbb     bbb          
           dbd     dbdbb                 bdbdb     bdb           
            bbb       bdbbd           bdbbb       bdb            
             bdbb        bbbbbdbdbbdbbdb        bdbb             
               bdbb                           bdbb               
                 bdbbd                     bdbbb                 
                    dbbbbd             bbdbbb                    
                            bdbbbbdbd """,
	"""                                         
                            bbbbbbbbb                            
                           bdb     dbd                           
                           bb dbdbd bb                           
                           bd bb bb bd                           
                    bbbbd  bb db db bb  bbbbb                    
                 bbdbd bb  db bd bd db  bd dbdbb                 
               bbdb    db  bb bb bb bb  bb    bdbb               
             bbdb     bbb  db db db bd  dbb     bdbb             
            bdb    bbbdb   bd bd bd bb   bdbbd    bdb            
           bbb    bdb      bb bbbbb db      dbb    bbd           
         bbd    bdb        dbd     bbd        bbb    bbb         
         bd     bb          bbbdbdbdb          db     db         
        dbb    bdb                             bdb    bbd        
        bb     bb                               bb     bb        
        bd     db                               bd     db        
        bb     bdb                             bdb     bd        
        dbb     bb                             bb     bbb        
         bd     dbd                           bdb     db         
          bbb     bbd                       bbd     bbb          
           dbd     bbbbd                 bdbdb     bdb           
            bbb       dbbbd           bbdbb       bdb            
             dbbd        bbbbdbbdbbbbdbd        bbbb             
               bbbd                           bbdb               
                 bbbdb                     bbbdb                 
                    bbbdbb             bbbbdb                    
                            dbbdbbdbb """,
	"""                                                                 
                            bbbbbbbbb                            
                            bd     db                            
                            bb dbd bd                            
                            db bbb db                            
                    bbbbb   bb dbd bb   bbbdb                    
                 bbdbd db   bd bbb bd   db bbbdb                 
               bbdb    bb   bb bdb bb   bb    bbbb               
             bbdb     bdb   db dbb db   bdb     dbdb             
            bdb    bbdbb    bd bbd bd    bdbdb    bbb            
           bbb    bdb       bb bdb bb       bbd    dbd           
         bbd    bdb         db     bd         bbb    bbb         
         bd     bb          bdbbbbdbb          db     db         
        dbb    bdd                             bdb    bbd        
        bb     bb                               bb     bb        
        bd     db                               bd     db        
        bb     bbd                             bdb     bb        
        dbb     bb                             bb     bdb        
         bd     dbb                           dbd     bb         
          bbb     dbb                       bbb     bdb          
           dbd     bdbbd                 bbdbd     bbb           
            bbb       bbbbb           bdbdb       bdb            
             bdbb        dbdbbdbbdbbdbbb        bbdb             
               bdbb                           bbdb               
                 bdbbd                     bbbdb                 
                    bbbdbb             bdbbdb                    
                            bbdbbbdbb """,
	"""                                                                 
                              bbbbb                              
                              bd db                              
                              bb bd                              
                              db bb                              
                    bbbbb     bb db     bbbbb                    
                 bbdbdbdb     bd bd     dbdbdbbb                 
               bbdbbbbbdb     bb bb     bdbbbdbdbb               
             bbdbbdbdbdbb     db db     bbdbbbdbbdbb             
            bdbbdbbbbbdb      bd bd      bbdbdbbbbdbd            
           bbbdbbbdbd         bb bb         bbbdbdbbbb           
         bbdbdbbdbb           db db           dbbbbdbdbb         
         bdbbbbbbd            bdbbb            bdbdbbbbd         
        bdbdbdbdbb                             bbbbbdbdbb        
        bbbbbbbbd                               dbdbbbbbd        
        bdbdbdbdb                               bbbdbdbdb        
        bbbdbbdbbd                             bdbdbbbbbb        
        dbdbbdbbbb                             bbbbbdbdbd        
         bbbbbbddbb                           dbdbdbbdbb         
          bdbdbbbdbbb                       dbbbbdbbbbb          
           bbdbdbbdbdbbb                 bdbbbdbdbbdbd           
            bdbbbbbbbdbdbbb           bdbbbbdbbbbdbbb            
             bbdbdbdbbbbdbdbbdbbbdbbdbbbdbdbbdbdbbbd             
               bbbdbbdbdbbbdbbdbdbbbbdbbbbbdbbbbdb               
                 dbbdbbbbdbbbdbbbbdbdbbdbdbbbdbb                 
                    bbdbdbbdbbbdbbbbbdbbdbbdb                    
                            bdbbdbdbd """,
	"""                                                                 
                            bbbbbbbbb                            
                            bdbdbdbdb                            
                            bbbdbbbdb                            
                            dbdbbdbbd                            
                    bbbbb   bbbbdbbbb   bbdbb                    
                 bbdbdbdb   bdbdbbdbd   dbbbdbbb                 
               bbdbbbbbbd   bbbbbdbbb   bbdbbdbdbb               
             bbdbbdbdbdbb   dbdbdbbdb   bbbdbbbbdbdb             
            bdbbdbbbbbbd    bbbbbbdbb    dbbbdbdbbbbd            
           bbbdbbdbdb       bdbddbbbd       bbbbbdbdbb           
         bbdbbbbbbd         bdbbbbdbb         dbdbbbbdbb         
         bdbdbdbdb          bbbdbdbbd          bbbdbdbbd         
        bdbbbbbdbb                             dbdbbbbbbb        
        bbbdbdbbb                               bbbdbdbdb        
        bdbbbdbdb                               bdbbbbdbb        
        bbdbbbdbbd                             bdbbdbdbbd        
        dbbdbbbdbb                             bdbbbbbbdb        
         bbbdbbbdbb                           bdbbdbdbdb         
          dbbdbdbbdbd                       dbbbbdbbbbb          
           bbbbbbdbbbbbd                 bbbbdbdbbbdbd           
            dbdbbbbdbdbbbdb           bbdbdbdbbbdbbbd            
             bdbdbdbbbdbbbbdbbdbbdbbdbdbbdbbbbdbbdbd             
               bbbbbdbbdbdbbdbbdbbbdbbbbdbbdbdbbdb               
                 dbdbbbbbbdbbdbbbdbbbdbbbbdbbbbd                 
                    bdbdbdbbbbbdbbbdbbdbdbbbd                    
                            dbdbbdbbd """,
	"""                                                                 
                            bbbbdbbbb                            
                           bdbdbbdbdbd                           
                           bdbbdbbbbbb                           
                           bbbdb bdbdb                           
                    bbbbd  bdbbb bbbbd  bbbbb                    
                 bbdbdbdb  bbdbd dbdbb  bdbdbdbb                 
               bbdbbbbbbb  dbbbb bbbdb  bdbbbbdbbd               
             bbdbbbdbdbdb  bbdbd bdbbb  bbdbdbbdbbbb             
            bdbbdbdbbbbb   dbbbb bbdbd   bbbbdbbbdbdb            
           bbbdbbbbbd      bbdbdbdbbbb      dbbdbbbbdb           
         bbdbdbbdbd        dbbbbbdbdbd        bbdbdbbbdb         
         bdbbbbbbb          bdbdbbbbb          bbbbdbbbd         
        bdbbdbdbdb                             dbdbbddbbb        
        bbbbbbbdb                               bbdbbbbdb        
        bdbdbdbbb                               bdbbdbbbd        
        bbdbbbdbdb                             bdbbbbdbdb        
        dbbbdbbbbd                             bdbdbbbbbb        
         bdbbdbdbbb                           dbbbbdbdbd         
          bbdbbbdbdbb                       dbbbdbbbbbd          
           bdbbdbbbdbdbb                 bdbbbdbbdbdbd           
            bdbbbdbbbbdbdbb           bdbbbdbbbdbbbbb            
             bbdbbbdbbbbbdbdbbdbbdbbdbdbbdbbdbdbbddb             
               bdbbbdbdbdbbbdbbbbbdbbbbbdbbbbbbbdb               
                 bdbbbdbbbdbbbdbdbbbdbdbbbdbdbdb                 
                    dbbbdbbbdbbbbdbbbbbdbdbbb                    
                            bdbdbdbdb """,
	"""                                                                 
                            bdbbbbbbb                            
                          bbbbdbdbdbdbb                          
                          bdbdbbbbdbbdb                          
                          bbdbb   bdbbd                          
                    bbbbd bdbbd   bbbdb bbdbb                    
                 bbdbdbdb bbbbb   dbdbb bdbbdbbb                 
               bbdbbbbbbb dbdbd   bbbbd bbbdbbdbdb               
             bbdbbdbdbdbd bbbbb   bdbbb dbbbbdbbbbdb             
            bdbbdbbbbdbb  bdbdb   bbdbd  bdbdbbdbbbdb            
           bbbdbbdbdb     bbbbdbbdbdbbb     bbbbdbdbbd           
         bdbdbbbbbb       dbdbdbbbbbdbb       dbbbbdbbbb         
         bbbbdbdbd          bbbdbdbdb          bdbdbbdbd         
        bdbdbbbbdb                             bbbbbdbbbb        
        bdbbdbdbb                               dbdbbbdbd        
        bbbdbbbdb                               bbbdbbbbb        
        dbbbbdbbbd                             bdbdbbdbdb        
        bdbdbbbdbb                             bbbbdbbbbd        
         bbbdbdbbdb                           bdbdbbbdbd         
          dbbbbdbbbbd                       bdbbdbbdbbb          
           bdbbbdbdbbbbb                 bbdbbdbbbdbbd           
            bdbbbbbdbdbdbbd           bbdbbbdbbbdbbbd            
             bdbdbdbbbbbdbbbbbdbbbdbbbdbbdbdbbdbbbdb             
               bbbbbdbdbbbdbdbbbdbbbdbbdbbbbbbbdbd               
                 dbdbbbdbbbbbdbdbbdbbdbbdbdbdbdb                 
                    bdbbdbdbdbbbbdbbbbdbbbbbb                    
                            bbdbdbbdb  """,
	"""                                                                 
                            bbbbdbbbb                            
                           bdbdbbdbdbd                           
                           bdbbdbbbbbb                           
                           bbbdb bdbdb                           
                    bbbbd  bdbbb bbbbd  bbbbb                    
                 bbdbdbdb  bbdbd dbdbb  bdbdbdbb                 
               bbdbbbbbbb  dbbbb bbbdb  bdbbbbdbbd               
             bbdbbbdbdbdb  bbdbd bdbbb  bbdbdbbdbbbb             
            bdbbdbdbbbbb   dbbbb bbdbd   bbbbdbbbdbdb            
           bbbdbbbbbd      bbdbdbdbbbb      dbbdbbbbdb           
         bbdbdbbdbd        dbbbbbdbdbd        bbdbdbbbdb         
         bdbbbbbbb          bdbdbbbbb          bbbbdbbbd         
        bdbbdbdbdb                             dbdbbddbbb        
        bbbbbbbdb                               bbdbbbbdb        
        bdbdbdbbb                               bdbbdbbbd        
        bbdbbbdbdb                             bdbbbbdbdb        
        dbbbdbbbbd                             bdbdbbbbbb        
         bdbbdbdbbb                           dbbbbdbdbd         
          bbdbbbdbdbb                       dbbbdbbbbbd          
           bdbbdbbbdbdbb                 bdbbbdbbdbdbd           
            bdbbbdbbbbdbdbb           bdbbbdbbbdbbbbb            
             bbdbbbdbbbbbdbdbbdbbdbbdbdbbdbbdbdbbddb             
               bdbbbdbdbdbbbdbbbbbdbbbbbdbbbbbbbdb               
                 bdbbbdbbbdbbbdbdbbbdbdbbbdbdbdb                 
                    dbbbdbbbdbbbbdbbbbbdbdbbb                    
                            bdbdbdbdb """,
	"""                                                                 
                            bbbbbbbbb                            
                            bdbdbdbdb                            
                            bbbdbbbdb                            
                            dbdbbdbbd                            
                    bbbbb   bbbbdbbbb   bbdbb                    
                 bbdbdbdb   bdbdbbdbd   dbbbdbbb                 
               bbdbbbbbbd   bbbbbdbbb   bbdbbdbdbb               
             bbdbbdbdbdbb   dbdbdbbdb   bbbdbbbbdbdb             
            bdbbdbbbbbbd    bbbbbbdbb    dbbbdbdbbbbd            
           bbbdbbdbdb       bdbddbbbd       bbbbbdbdbb           
         bbdbbbbbbd         bdbbbbdbb         dbdbbbbdbb         
         bdbdbdbdb          bbbdbdbbd          bbbdbdbbd         
        bdbbbbbdbb                             dbdbbbbbbb        
        bbbdbdbbb                               bbbdbdbdb        
        bdbbbdbdb                               bdbbbbdbb        
        bbdbbbdbbd                             bdbbdbdbbd        
        dbbdbbbdbb                             bdbbbbbbdb        
         bbbdbbbdbb                           bdbbdbdbdb         
          dbbdbdbbdbd                       dbbbbdbbbbb          
           bbbbbbdbbbbbd                 bbbbdbdbbbdbd           
            dbdbbbbdbdbbbdb           bbdbdbdbbbdbbbd            
             bdbdbdbbbdbbbbdbbdbbdbbdbdbbdbbbbdbbdbd             
               bbbbbdbbdbdbbdbbdbbbdbbbbdbbdbdbbdb               
                 dbdbbbbbbdbbdbbbdbbbdbbbbdbbbbd                 
                    bdbdbdbbbbbdbbbdbbdbdbbbd                    
                            dbdbbdbbd """,
	"""                                                                 
                              bbbbb                              
                              bdbdb                              
                              bbdbb                              
                              dbbbd                              
                    bbbbb     bbdbb     bbbdb                    
                 bbdbd db     bdbbd     db bbbbb                 
               bbdb    bd     bbbdb     bb    dbdb               
             bbdb     bbb     dbbbb     bdb     bbbd             
            bdb    bbbdb      bdbdb      bdbdb    dbb            
           bbd    bdb         bbbbd         bdb    bbb           
         bdb    bdb           bdbdb           bdb    dbb         
         bb     bb            bbdbb            bb     bd         
        bdb    bdb                             bdb    bbb        
        bd     bb                               bd     db        
        bb     db                               bb     bd        
        db     bbd                             bdb     bb        
        bbd     bb                             bb     bdb        
         bb     dbd                           bdb     bb         
          dbb     bbd                       dbb     bdb          
           bdb     bbbbb                 bdbbd     dbb           
            bdb       dbdbb           bdbbb       bbd            
             bbdb        bdbdbbdbbdbbdbb        bddb             
               bbbd                           bdbb               
                 dbbdb                     dbbdb                 
                    bbdbbb             bdbbbd                    
                            bbdbbbdbb """,
	"""                                                                 
                            bbbbbbbbb                            
                            bd     db                            
                            bb dbd bd                            
                            db bbb db                            
                    bbbbb   bb dbd bb   bbbdb                    
                 bbdbd db   bd bbb bd   db bbbdb                 
               bbdb    bb   bb bdb bb   bb    bbbb               
             bbdb     bdb   db dbb db   bdb     dbdb             
            bdb    bbdbb    bd bbd bd    bdbdb    bbb            
           bbb    bdb       bb bdb bb       bbd    dbd           
         bbd    bdb         db     bd         bbb    bbb         
         bd     bb          bdbbbbdbb          db     db         
        dbb    bdd                             bdb    bbd        
        bb     bb                               bb     bb        
        bd     db                               bd     db        
        bb     bbd                             bdb     bb        
        dbb     bb                             bb     bdb        
         bd     dbb                           dbd     bb         
          bbb     dbb                       bbb     bdb          
           dbd     bdbbd                 bbdbd     bbb           
            bbb       bbbbb           bdbdb       bdb            
             bdbb        dbdbbdbbdbbdbbb        bbdb             
               bdbb                           bbdb               
                 bdbbd                     bbbdb                 
                    bbbdbb             bdbbdb                    
                            bbdbbbdbb """,
    """                                                                 
                            bbbbbbbbb                            
                           bdb     dbd                           
                           bb dbdbd bb                           
                           bd bb bb bd                           
                    bbbbd  bb db db bb  bbbbb                    
                 bbdbd bb  db bd bd db  bd dbdbb                 
               bbdb    db  bb bb bb bb  bb    bdbb               
             bbdb     bbb  db db db bd  dbb     bdbb             
            bdb    bbbdb   bd bd bd bb   bdbbd    bdb            
           bbb    bdb      bb bbbbb db      dbb    bbd           
         bbd    bdb        dbd     bbd        bbb    bbb         
         bd     bb          bbbdbdbdb          db     db         
        dbb    bdb                             bdb    bbd        
        bb     bb                               bb     bb        
        bd     db                               bd     db        
        bb     bdb                             bdb     bd        
        dbb     bb                             bb     bbb        
         bd     dbd                           bdb     db         
          bbb     bbd                       bbd     bbb          
           dbd     bbbbd                 bdbdb     bdb           
            bbb       dbbbd           bbdbb       bdb            
             dbbd        bbbbdbbdbbbbdbd        bbbb             
               bbbd                           bbdb               
                 bbbdb                     bbbdb                 
                    bbbdbb             bbbbdb                    
                            dbbdbbdbb """,
    """                                                                 
                            bbbbbbbbb                            
                          bbdb     dbdb                          
                          bd  dbdbd  bb                          
                          bb bb   bb db                          
                    bbbbd bd bd   bd bb dbbbb                    
                 bbdbd bb bb bb   bb bd bb dbdbb                 
               bbdb    bd bd bd   db bb bd    bdbb               
             bbdb     bdb bb bb   bb db dbb     dbdb             
            bdb    bbdbb  db db   bd bd  bbbdb    bbd            
           bbb    bdb     bb bdbdbbb bb     bbb    bbd           
         bbd    bdb       bdbb     dbdb       dbb    bbb         
         bd     bb          bdbbbdbbb          bd     db         
        bdb    dbd                             bbb    bdb        
        bb     bb                               db     bb        
        bd     bd                               bd     db        
        bb     bbb                             bdb     bd        
        dbb     db                             bb     bbb        
         bd     bbd                           dbd     db         
          bbb     bbb                       bbb     bbb          
           dbd     dbdbb                 bdbdb     bdb           
            bbb       bdbbd           bdbbb       bdb            
             bdbb        bbbbbdbdbbdbbdb        bdbb             
               bdbb                           bdbb               
                 bdbbd                     bdbbb                 
                    dbbbbd             bbdbbb                    
                            bdbbbbdbd  """,
    """
                            bbbbbbbbb                            
                           bdb     dbd                           
                           bb dbdbd bb                           
                           bd bb bb bd                           
                    bbbbd  bb db db bb  bbbbb                    
                 bbdbd bb  db bd bd db  bd dbdbb                 
               bbdb    db  bb bb bb bb  bb    bdbb               
             bbdb     bbb  db db db bd  dbb     bdbb             
            bdb    bbbdb   bd bd bd bb   bdbbd    bdb            
           bbb    bdb      bb bbbbb db      dbb    bbd           
         bbd    bdb        dbd     bbd        bbb    bbb         
         bd     bb          bbbdbdbdb          db     db         
        dbb    bdb                             bdb    bbd        
        bb     bb                               bb     bb        
        bd     db                               bd     db        
        bb     bdb                             bdb     bd        
        dbb     bb                             bb     bbb        
         bd     dbd                           bdb     db         
          bbb     bbd                       bbd     bbb          
           dbd     bbbbd                 bdbdb     bdb           
            bbb       dbbbd           bbdbb       bdb            
             dbbd        bbbbdbbdbbbbdbd        bbbb             
               bbbd                           bbdb               
                 bbbdb                     bbbdb                 
                    bbbdbb             bbbbdb                    
                            dbbdbbdbb """,
	"""                                                                 
                            bbbbbbbbb                            
                            bd     db                            
                            bb dbd bd                            
                            db bbb db                            
                    bbbbb   bb dbd bb   bbbdb                    
                 bbdbd db   bd bbb bd   db bbbdb                 
               bbdb    bb   bb bdb bb   bb    bbbb               
             bbdb     bdb   db dbb db   bdb     dbdb             
            bdb    bbdbb    bd bbd bd    bdbdb    bbb            
           bbb    bdb       bb bdb bb       bbd    dbd           
         bbd    bdb         db     bd         bbb    bbb         
         bd     bb          bdbbbbdbb          db     db         
        dbb    bdd                             bdb    bbd        
        bb     bb                               bb     bb        
        bd     db                               bd     db        
        bb     bbd                             bdb     bb        
        dbb     bb                             bb     bdb        
         bd     dbb                           dbd     bb         
          bbb     dbb                       bbb     bdb          
           dbd     bdbbd                 bbdbd     bbb           
            bbb       bbbbb           bdbdb       bdb            
             bdbb        dbdbbdbbdbbdbbb        bbdb             
               bdbb                           bbdb               
                 bdbbd                     bbbdb                 
                    bbbdbb             bdbbdb                    
                            bbdbbbdbb """,
	"""                                                                 
                              bbbbb                              
                              bd db                              
                              bb bd                              
                              db bb                              
                    bbbbb     bb db     bbbbb                    
                 bbdbdbdb     bd bd     dbdbdbbb                 
               bbdbbbbbdb     bb bb     bdbbbdbdbb               
             bbdbbdbdbdbb     db db     bbdbbbdbbdbb             
            bdbbdbbbbbdb      bd bd      bbdbdbbbbdbd            
           bbbdbbbdbd         bb bb         bbbdbdbbbb           
         bbdbdbbdbb           db db           dbbbbdbdbb         
         bdbbbbbbd            bdbbb            bdbdbbbbd         
        bdbdbdbdbb                             bbbbbdbdbb        
        bbbbbbbbd                               dbdbbbbbd        
        bdbdbdbdb                               bbbdbdbdb        
        bbbdbbdbbd                             bdbdbbbbbb        
        dbdbbdbbbb                             bbbbbdbdbd        
         bbbbbbddbb                           dbdbdbbdbb         
          bdbdbbbdbbb                       dbbbbdbbbbb          
           bbdbdbbdbdbbb                 bdbbbdbdbbdbd           
            bdbbbbbbbdbdbbb           bdbbbbdbbbbdbbb            
             bbdbdbdbbbbdbdbbdbbbdbbdbbbdbdbbdbdbbbd             
               bbbdbbdbdbbbdbbdbdbbbbdbbbbbdbbbbdb               
                 dbbdbbbbdbbbdbbbbdbdbbdbdbbbdbb                 
                    bbdbdbbdbbbdbbbbbdbbdbbdb                    
                            bdbbdbdbd """,
	"""                                                                 
                            bbbbbbbbb                            
                            bdbdbdbdb                            
                            bbbdbbbdb                            
                            dbdbbdbbd                            
                    bbbbb   bbbbdbbbb   bbdbb                    
                 bbdbdbdb   bdbdbbdbd   dbbbdbbb                 
               bbdbbbbbbd   bbbbbdbbb   bbdbbdbdbb               
             bbdbbdbdbdbb   dbdbdbbdb   bbbdbbbbdbdb             
            bdbbdbbbbbbd    bbbbbbdbb    dbbbdbdbbbbd            
           bbbdbbdbdb       bdbddbbbd       bbbbbdbdbb           
         bbdbbbbbbd         bdbbbbdbb         dbdbbbbdbb         
         bdbdbdbdb          bbbdbdbbd          bbbdbdbbd         
        bdbbbbbdbb                             dbdbbbbbbb        
        bbbdbdbbb                               bbbdbdbdb        
        bdbbbdbdb                               bdbbbbdbb        
        bbdbbbdbbd                             bdbbdbdbbd        
        dbbdbbbdbb                             bdbbbbbbdb        
         bbbdbbbdbb                           bdbbdbdbdb         
          dbbdbdbbdbd                       dbbbbdbbbbb          
           bbbbbbdbbbbbd                 bbbbdbdbbbdbd           
            dbdbbbbdbdbbbdb           bbdbdbdbbbdbbbd            
             bdbdbdbbbdbbbbdbbdbbdbbdbdbbdbbbbdbbdbd             
               bbbbbdbbdbdbbdbbdbbbdbbbbdbbdbdbbdb               
                 dbdbbbbbbdbbdbbbdbbbdbbbbdbbbbd                 
                    bdbdbdbbbbbdbbbdbbdbdbbbd                    
                            dbdbbdbbd """,
	"""                                                                 
                            bbbbdbbbb                            
                           bdbdbbdbdbd                           
                           bdbbdbbbbbb                           
                           bbbdb bdbdb                           
                    bbbbd  bdbbb bbbbd  bbbbb                    
                 bbdbdbdb  bbdbd dbdbb  bdbdbdbb                 
               bbdbbbbbbb  dbbbb bbbdb  bdbbbbdbbd               
             bbdbbbdbdbdb  bbdbd bdbbb  bbdbdbbdbbbb             
            bdbbdbdbbbbb   dbbbb bbdbd   bbbbdbbbdbdb            
           bbbdbbbbbd      bbdbdbdbbbb      dbbdbbbbdb           
         bbdbdbbdbd        dbbbbbdbdbd        bbdbdbbbdb         
         bdbbbbbbb          bdbdbbbbb          bbbbdbbbd         
        bdbbdbdbdb                             dbdbbddbbb        
        bbbbbbbdb                               bbdbbbbdb        
        bdbdbdbbb                               bdbbdbbbd        
        bbdbbbdbdb                             bdbbbbdbdb        
        dbbbdbbbbd                             bdbdbbbbbb        
         bdbbdbdbbb                           dbbbbdbdbd         
          bbdbbbdbdbb                       dbbbdbbbbbd          
           bdbbdbbbdbdbb                 bdbbbdbbdbdbd           
            bdbbbdbbbbdbdbb           bdbbbdbbbdbbbbb            
             bbdbbbdbbbbbdbdbbdbbdbbdbdbbdbbdbdbbddb             
               bdbbbdbdbdbbbdbbbbbdbbbbbdbbbbbbbdb               
                 bdbbbdbbbdbbbdbdbbbdbdbbbdbdbdb                 
                    dbbbdbbbdbbbbdbbbbbdbdbbb                    
                            bdbdbdbdb """,
	"""                                                                 
                            bdbbbbbbb                            
                          bbbbdbdbdbdbb                          
                          bdbdbbbbdbbdb                          
                          bbdbb   bdbbd                          
                    bbbbd bdbbd   bbbdb bbdbb                    
                 bbdbdbdb bbbbb   dbdbb bdbbdbbb                 
               bbdbbbbbbb dbdbd   bbbbd bbbdbbdbdb               
             bbdbbdbdbdbd bbbbb   bdbbb dbbbbdbbbbdb             
            bdbbdbbbbdbb  bdbdb   bbdbd  bdbdbbdbbbdb            
           bbbdbbdbdb     bbbbdbbdbdbbb     bbbbdbdbbd           
         bdbdbbbbbb       dbdbdbbbbbdbb       dbbbbdbbbb         
         bbbbdbdbd          bbbdbdbdb          bdbdbbdbd         
        bdbdbbbbdb                             bbbbbdbbbb        
        bdbbdbdbb                               dbdbbbdbd        
        bbbdbbbdb                               bbbdbbbbb        
        dbbbbdbbbd                             bdbdbbdbdb        
        bdbdbbbdbb                             bbbbdbbbbd        
         bbbdbdbbdb                           bdbdbbbdbd         
          dbbbbdbbbbd                       bdbbdbbdbbb          
           bdbbbdbdbbbbb                 bbdbbdbbbdbbd           
            bdbbbbbdbdbdbbd           bbdbbbdbbbdbbbd            
             bdbdbdbbbbbdbbbbbdbbbdbbbdbbdbdbbdbbbdb             
               bbbbbdbdbbbdbdbbbdbbbdbbdbbbbbbbdbd               
                 dbdbbbdbbbbbdbdbbdbbdbbdbdbdbdb                 
                    bdbbdbdbdbbbbdbbbbdbbbbbb                    
                            bbdbdbbdb  """,
	"""                                                                 
                            bbbbdbbbb                            
                           bdbdbbdbdbd                           
                           bdbbdbbbbbb                           
                           bbbdb bdbdb                           
                    bbbbd  bdbbb bbbbd  bbbbb                    
                 bbdbdbdb  bbdbd dbdbb  bdbdbdbb                 
               bbdbbbbbbb  dbbbb bbbdb  bdbbbbdbbd               
             bbdbbbdbdbdb  bbdbd bdbbb  bbdbdbbdbbbb             
            bdbbdbdbbbbb   dbbbb bbdbd   bbbbdbbbdbdb            
           bbbdbbbbbd      bbdbdbdbbbb      dbbdbbbbdb           
         bbdbdbbdbd        dbbbbbdbdbd        bbdbdbbbdb         
         bdbbbbbbb          bdbdbbbbb          bbbbdbbbd         
        bdbbdbdbdb                             dbdbbddbbb        
        bbbbbbbdb                               bbdbbbbdb        
        bdbdbdbbb                               bdbbdbbbd        
        bbdbbbdbdb                             bdbbbbdbdb        
        dbbbdbbbbd                             bdbdbbbbbb        
         bdbbdbdbbb                           dbbbbdbdbd         
          bbdbbbdbdbb                       dbbbdbbbbbd          
           bdbbdbbbdbdbb                 bdbbbdbbdbdbd           
            bdbbbdbbbbdbdbb           bdbbbdbbbdbbbbb            
             bbdbbbdbbbbbdbdbbdbbdbbdbdbbdbbdbdbbddb             
               bdbbbdbdbdbbbdbbbbbdbbbbbdbbbbbbbdb               
                 bdbbbdbbbdbbbdbdbbbdbdbbbdbdbdb                 
                    dbbbdbbbdbbbbdbbbbbdbdbbb                    
                            bdbdbdbdb """,
	"""                                                                 
                            bbbbbbbbb                            
                            bdbdbdbdb                            
                            bbbdbbbdb                            
                            dbdbbdbbd                            
                    bbbbb   bbbbdbbbb   bbdbb                    
                 bbdbdbdb   bdbdbbdbd   dbbbdbbb                 
               bbdbbbbbbd   bbbbbdbbb   bbdbbdbdbb               
             bbdbbdbdbdbb   dbdbdbbdb   bbbdbbbbdbdb             
            bdbbdbbbbbbd    bbbbbbdbb    dbbbdbdbbbbd            
           bbbdbbdbdb       bdbddbbbd       bbbbbdbdbb           
         bbdbbbbbbd         bdbbbbdbb         dbdbbbbdbb         
         bdbdbdbdb          bbbdbdbbd          bbbdbdbbd         
        bdbbbbbdbb                             dbdbbbbbbb        
        bbbdbdbbb                               bbbdbdbdb        
        bdbbbdbdb                               bdbbbbdbb        
        bbdbbbdbbd                             bdbbdbdbbd        
        dbbdbbbdbb                             bdbbbbbbdb        
         bbbdbbbdbb                           bdbbdbdbdb         
          dbbdbdbbdbd                       dbbbbdbbbbb          
           bbbbbbdbbbbbd                 bbbbdbdbbbdbd           
            dbdbbbbdbdbbbdb           bbdbdbdbbbdbbbd            
             bdbdbdbbbdbbbbdbbdbbdbbdbdbbdbbbbdbbdbd             
               bbbbbdbbdbdbbdbbdbbbdbbbbdbbdbdbbdb               
                 dbdbbbbbbdbbdbbbdbbbdbbbbdbbbbd                 
                    bdbdbdbbbbbdbbbdbbdbdbbbd                    
                            dbdbbdbbd """,
	"""                                                                 
                              bbbbb                              
                              bdbdb                              
                              bbdbb                              
                              dbbbd                              
                    bbbbb     bbdbb     bbbdb                    
                 bbdbd db     bdbbd     db bbbbb                 
               bbdb    bd     bbbdb     bb    dbdb               
             bbdb     bbb     dbbbb     bdb     bbbd             
            bdb    bbbdb      bdbdb      bdbdb    dbb            
           bbd    bdb         bbbbd         bdb    bbb           
         bdb    bdb           bdbdb           bdb    dbb         
         bb     bb            bbdbb            bb     bd         
        bdb    bdb                             bdb    bbb        
        bd     bb                               bd     db        
        bb     db                               bb     bd        
        db     bbd                             bdb     bb        
        bbd     bb                             bb     bdb        
         bb     dbd                           bdb     bb         
          dbb     bbd                       dbb     bdb          
           bdb     bbbbb                 bdbbd     dbb           
            bdb       dbdbb           bdbbb       bbd            
             bbdb        bdbdbbdbbdbbdbb        bddb             
               bbbd                           bdbb               
                 dbbdb                     dbbdb                 
                    bbdbbb             bdbbbd                    
                            bbdbbbdbb """,
	"""                                                                 
                            bbbbbbbbb                            
                            bd     db                            
                            bb dbd bd                            
                            db bbb db                            
                    bbbbb   bb dbd bb   bbbdb                    
                 bbdbd db   bd bbb bd   db bbbdb                 
               bbdb    bb   bb bdb bb   bb    bbbb               
             bbdb     bdb   db dbb db   bdb     dbdb             
            bdb    bbdbb    bd bbd bd    bdbdb    bbb            
           bbb    bdb       bb bdb bb       bbd    dbd           
         bbd    bdb         db     bd         bbb    bbb         
         bd     bb          bdbbbbdbb          db     db         
        dbb    bdd                             bdb    bbd        
        bb     bb                               bb     bb        
        bd     db                               bd     db        
        bb     bbd                             bdb     bb        
        dbb     bb                             bb     bdb        
         bd     dbb                           dbd     bb         
          bbb     dbb                       bbb     bdb          
           dbd     bdbbd                 bbdbd     bbb           
            bbb       bbbbb           bdbdb       bdb            
             bdbb        dbdbbdbbdbbdbbb        bbdb             
               bdbb                           bbdb               
                 bdbbd                     bbbdb                 
                    bbbdbb             bdbbdb                    
                            bbdbbbdbb """,
    """                                                                 
                            bbbbbbbbb                            
                           bdb     dbd                           
                           bb dbdbd bb                           
                           bd bb bb bd                           
                    bbbbd  bb db db bb  bbbbb                    
                 bbdbd bb  db bd bd db  bd dbdbb                 
               bbdb    db  bb bb bb bb  bb    bdbb               
             bbdb     bbb  db db db bd  dbb     bdbb             
            bdb    bbbdb   bd bd bd bb   bdbbd    bdb            
           bbb    bdb      bb bbbbb db      dbb    bbd           
         bbd    bdb        dbd     bbd        bbb    bbb         
         bd     bb          bbbdbdbdb          db     db         
        dbb    bdb                             bdb    bbd        
        bb     bb                               bb     bb        
        bd     db                               bd     db        
        bb     bdb                             bdb     bd        
        dbb     bb                             bb     bbb        
         bd     dbd                           bdb     db         
          bbb     bbd                       bbd     bbb          
           dbd     bbbbd                 bdbdb     bdb           
            bbb       dbbbd           bbdbb       bdb            
             dbbd        bbbbdbbdbbbbdbd        bbbb             
               bbbd                           bbdb               
                 bbbdb                     bbbdb                 
                    bbbdbb             bbbbdb                    
                            dbbdbbdbb """,
    """                                                                 
                            bbbbbbbbb                            
                          bbdb     dbdb                          
                          bd  dbdbd  bb                          
                          bb bb   bb db                          
                    bbbbd bd bd   bd bb dbbbb                    
                 bbdbd bb bb bb   bb bd bb dbdbb                 
               bbdb    bd bd bd   db bb bd    bdbb               
             bbdb     bdb bb bb   bb db dbb     dbdb             
            bdb    bbdbb  db db   bd bd  bbbdb    bbd            
           bbb    bdb     bb bdbdbbb bb     bbb    bbd           
         bbd    bdb       bdbb     dbdb       dbb    bbb         
         bd     bb          bdbbbdbbb          bd     db         
        bdb    dbd                             bbb    bdb        
        bb     bb                               db     bb        
        bd     bd                               bd     db        
        bb     bbb                             bdb     bd        
        dbb     db                             bb     bbb        
         bd     bbd                           dbd     db         
          bbb     bbb                       bbb     bbb          
           dbd     dbdbb                 bdbdb     bdb           
            bbb       bdbbd           bdbbb       bdb            
             bdbb        bbbbbdbdbbdbbdb        bdbb             
               bdbb                           bdbb               
                 bdbbd                     bdbbb                 
                    dbbbbd             bbdbbb                    
                            bdbbbbdbd  """,

	]

    for frame in power_frames:
        clear_screen()
        print(random_color() + frame + reset_color())
        time.sleep(0.03)

    clear_screen()
    display_ascii_art()

# Function to display ASCII art after clearing the screen with random colors
def display_ascii_art():
    ascii_art = """                                                                 
                            bdbbbbbbb                            
                          bbbbdbdbdbdbb                          
                          bdbdbbbbdbbdb                          
                          bbdbb   bdbbd                          
                    bbbbd bdbbd   bbbdb bbdbb                    
                 bbdbdbdb bbbbb   dbdbb bdbbdbbb                 
               bbdbbbbbbb dbdbd   bbbbd bbbdbbdbdb               
             bbdbbdbdbdbd bbbbb   bdbbb dbbbbdbbbbdb             
            bdbbdbbbbdbb  bdbdb   bbdbd  bdbdbbdbbbdb            
           bbbdbbdbdb     bbbbdbbdbdbbb     bbbbdbdbbd           
         bdbdbbbbbb       dbdbdbbbbbdbb       dbbbbdbbbb         
         bbbbdbdbd          bbbdbdbdb          bdbdbbdbd         
        bdbdbbbbdb                             bbbbbdbbbb        
        bdbbdbdbb                               dbdbbbdbd        
        bbbdbbbdb                               bbbdbbbbb        
        dbbbbdbbbd                             bdbdbbdbdb        
        bdbdbbbdbb                             bbbbdbbbbd        
         bbbdbdbbdb                           bdbdbbbdbd         
          dbbbbdbbbbd                       bdbbdbbdbbb          
           bdbbbdbdbbbbb                 bbdbbdbbbdbbd           
            bdbbbbbdbdbdbbd           bbdbbbdbbbdbbbd            
             bdbdbdbbbbbdbbbbbdbbbdbbbdbbdbdbbdbbbdb             
               bbbbbdbdbbbdbdbbbdbbbdbbdbbbbbbbdbd               
                 dbdbbbdbbbbbdbdbbdbbdbbdbdbdbdb                 
                    bdbbdbdbdbbbbdbbbbdbbbbbb                    
                            bbdbdbbdb  
    """
    colored_art = ''.join(random_color() + char + reset_color() for char in ascii_art)
    print(colored_art)

# Function for something to look at
def custom_animation():
    """Display the custom animation with marquee effect on the same line."""
    marquee_text = "Following the rabbit... "
    marquee_length = 30
    marquee_position = 0
    animation_on = True
    while animation_on:
        # Create the display text for the marquee
        display_text = marquee_text[marquee_position:marquee_position + marquee_length].ljust(marquee_length)
        # Move cursor back to the start of the line and print the display text
        sys.stdout.write('\r' + display_text)
        sys.stdout.flush()
        # Update the position for the next frame
        marquee_position = (marquee_position + 1) % len(marquee_text)
        # Sleep to create the animation effect
        time.sleep(0.1)
        # Stop the animation if done is True
        if done:
            animation_on = False
    # Clear the line after animation ends
    sys.stdout.write('\r' + ' ' * marquee_length + '\r')
    sys.stdout.flush()

# Correctly formatted frames list
frames = [
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   n n| \n"+
	"   / /  /`   `'.= Y)= \n"+
	"  ( (  /        `\"`} \n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   n n|\n"+
	"   / /  /`   `'.= Y)=\n"+
	"  ( (  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   a a|\n"+
	"   / /  /`   `'.= y)=\n"+
	"  ( (  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   a a| \n"+
	"   / /  /`   `'.= y)=\n"+
	"  ( (  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"               ,-.\n"+
	"              /\\\\_\\ \n"+
	"     _       /     \\ \n"+
	"    / )   __|   a a|\n"+
	"   / /  /`   `'.= y)=\n"+
	"  ( (  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"               ,-.\n"+
	"              /\\\\_\\ \n"+
	"     _       /     \\ \n"+
	"    / )   __|   a a|\n"+
	"   / /  /`   `'.= y)=\n"+
	"  ( (  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"            ,-.,-.\n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|   a a|\n"+
	"   _    /`   `'.= y)=\n"+
	"  ( \\  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"       (__,,)) \\_)_)",
	"            ,-.,-.\n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"   _    /`   `'. = y)=\n"+
	"  ( \\  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"       (__,,)) \\_)_)",
	"              ,-.\n"+
	"            ,-.\\ \\ \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"    _  /        `\"`}\n"+
	"   ( \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( ( \n"+
	"       (____)  \\_)_)",
	"              ,-.\n"+
	"            ,-.\\ \\ \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"    _  /        `\"`}\n"+
	"   ( \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"       (____)  \\_)_)",
	"              ,-.\n"+
	"            ,-.\\ \\ \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"       /        `\"`}\n"+
	"     _|    \\       }\n"+
	"    ( \\     ),   //\n"+
	"     '._,  /__\\ ( ( \n"+
	"       (______)\\_)_)",
	"           ,-.,-.\n"+
	"            \\ \\\\ \\ \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"       /        `\"`}\n"+
	"     _|    \\       }\n"+
	"    ( \\     ),   //\n"+
	"     '._,  /__\\ ( (\n"+
	"       (______)\\_)_)",
	"           ,-.,-. \n"+
	"            \\ \\\\ \\ \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"       /        `\"`}\n"+
	"     _|    \\       }\n"+
	"    { \\     ),   //\n"+
	"     '-',  /__\\ ( ( \n"+
	"       (______)\\_)_)",
	"           ,-.,-. \n"+
	"            \\ \\\\ \\ \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"       /        `\"`}\n"+
	"     _|    \\       }\n"+
	"    { \\     ),   //\n"+
	"     '-',  /__\\ ( (\n"+
	"       (______)\\_)_)",
	"           ,-.,-.\n"+
	"            \\ \\\\ \\ \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"       /        `\"`}\n"+
	"     _|    \\       }\n"+
	"    { \\     ),   //\n"+
	"     '-',  /__\\ ( (\n"+
	"       (______)\\_)_)",
	"           ,-.,-. \n"+
	"            \\ \\\\ \\ \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"       /        `\"`}\n"+
	"     _|    \\       }\n"+
	"    { \\     ),   //\n"+
	"     '-',  /__\\ ( (\n"+
	"       (______)\\_)_)",
	"           ,-.,-.\n"+
	"            \\ \\\\ \\ \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"       /        `\"`}\n"+
	"     _|    \\       }\n"+
	"    { \\     ),   //\n"+
	"     '-',  /__\\ ( (\n"+
	"       (______)\\_)_)",
	"           ,-.,-. \n"+
	"            \\ \\\\ \\ \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"       /        `\"`}\n"+
	"     _|    \\       }\n"+
	"    { \\     ),   //\n"+
	"     '-',  /__\\ ( (\n"+
	"       (______)\\_)_)",
	"           ,-.,-.\n"+
	"            \\ \\\\ \\ \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"       /        `\"`}\n"+
	"     _|    \\       }\n"+
	"    { \\     ),   //\n"+
	"     '-',  /__\\ ( (\n"+
	"       (______)\\_)_)",
	"           ,-. \n"+
	"            \\ \\,-. \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|    a a|\n"+
	"        /`   `'. = y)=\n"+
	"       /        `\"`}\n"+
	"     _|    \\       }\n"+
	"    ( \\     ),   //\n"+
	"     '._,  /__\\ ( ( \n"+
	"       (______)\\_)_)",
	"           ,-.  \n"+
	"            \\ \\,-. \n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|   a a|\n"+
	"        /`   `'.= y)=\n"+
	"    _  /        `\"`}\n"+
	"   ( \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"       (____)  \\_)_)",
	"            ,-.,-.\n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|   a a|\n"+
	"   _    /`   `'.= y)=\n"+
	"  ( \\  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"       (__,,)) \\_)_)",
	"            ,-.,-.\n"+
	"             \\ \\\\_\\ \n"+
	"             /     \\ \n"+
	"          __|   a a|\n"+
	"   _    /`   `'.= y)=\n"+
	"  ( \\  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"       (__,,)) \\_)_)",
	"             ,-. \n"+
	"              \\ \\/\\ \n"+
	"     _       /   ``\\ \n"+
	"    / )   __|   a a|\n"+
	"   / /  /`   `'.= y)=\n"+
	"  ( (  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"             ,-. \n"+
	"              \\ \\/\\ \n"+
	"     _       /   ``\\ \n"+
	"    / )   __|   a a|\n"+
	"   / /  /`   `'.= y)=\n"+
	"  ( (  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   a a|\n"+
	"   / /  /`   `'.= y)=\n"+
	"  ( (  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   a a| \n"+
	"   / /  /`   `'.= y)=\n"+
	"  ( (  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   n n| \n"+
	"   / /  /`   `'.= Y)= \n"+
	"  ( (  /        `\"`} \n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   n n| \n"+
	"   / /  /`   `'.= Y)= \n"+
	"  ( (  /        `\"`} \n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   n n| \n"+
	"   / /  /`   `'.= Y)= \n"+
	"  ( (  /        `\"`} \n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   n n| \n"+
	"   / /  /`   `'.= Y)= \n"+
	"  ( (  /        `\"`} \n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   n n| \n"+
	"   / /  /`   `'.= Y)= \n"+
	"  ( (  /        `\"`} \n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)",
	"    _         /\\_/\\ \n"+
	"   ( \\       /   ``\\ \n"+
	"    ) )   __|   n n|\n"+
	"   / /  /`   `'.= Y)=\n"+
	"  ( (  /        `\"`}\n"+
	"   \\ \\|    \\       }\n"+
	"    \\ \\     ),   //\n"+
	"     '._,  /'-\\ ( (\n"+
	"         \\,,)) \\,),)"]

# Function for t43 l33t
def intro():
    from colorama import Fore, Style, init

    init(autoreset=True)  # Initialize colorama for colored terminal output

    class FilteredStream(StringIO):
        def __init__(self):
            super().__init__()
            self._original = sys.stderr

        def write(self, message):
            # Filter out specific ALSA error messages
            if not message.startswith("ALSA lib pcm.c"):
                self._original.write(message)

        def flush(self):
            # Required for file-like objects
            self._original.flush()

    # ANSI escape codes for colors
    COLORS = [
        '\033[31m',  # Red
        '\033[33m',  # Yellow
        '\033[32m',  # Green
        '\033[36m',  # Cyan
        '\033[34m',  # Blue
        '\033[35m',  # Magenta
    ]

    GREEN = '\033[32m'  # Green color
    RESET = '\033[0m'  # Reset to default color

    def clear_screen():
        """Clear the terminal screen."""
        os.system('clear' if os.name != 'nt' else 'cls')

    def colorize_text(text, color):
        """Colorize the text with a specific color."""
        return color + text + RESET
    
    def animate_colors(text, colors, duration=1):
        """Animate text colors in a sequence for a specified duration."""
        start_time = time.time()
        while time.time() - start_time < duration:
            for color in colors:
                clear_screen()
                print(colorize_text(text, color))
                time.sleep(0.05)
        # Ensure the final color is shown
        clear_screen()
        print(colorize_text(text, colors[-1]))

    def fade_out_borders(ascii_art, border_art, duration=3, frame_rate=0.033):
        """Fade out the specified border areas of the ASCII art over a specified duration."""
        num_frames = int(duration / frame_rate)
        ascii_lines = ascii_art.split('\n')
        border_lines = border_art.split('\n')
        border_height = len(border_lines)
        
        num_rows = len(ascii_lines)
        max_line_length = max(len(line) for line in ascii_lines)
        
        border_top_rows = 3
        border_bottom_rows = 3
        border_left_chars = 7
        border_right_chars = 7
        
        for frame in range(num_frames):
            clear_screen()
            faded_art = []

            fade_amount = int(frame * (border_top_rows + border_bottom_rows) / num_frames)
            
            for i, line in enumerate(ascii_lines):
                if i < border_top_rows or i >= num_rows - border_bottom_rows:
                    if i < fade_amount:
                        faded_art.append(' ' * len(line))
                    else:
                        faded_art.append(line)
                else:
                    if len(line) > border_left_chars + border_right_chars:
                        left_part = line[:border_left_chars]
                        right_part = line[-border_right_chars:]
                        middle_part = line[border_left_chars:-border_right_chars]
                        
                        if frame < (num_frames / 2):
                            fade_progress = int(frame * (border_left_chars + border_right_chars) / (num_frames / 2))
                            if fade_progress <= border_left_chars:
                                left_part = ' ' * fade_progress + left_part[fade_progress:]
                            else:
                                left_part = ' ' * border_left_chars
                            if fade_progress <= border_right_chars:
                                right_part = right_part[:-fade_progress] + ' ' * fade_progress
                            else:
                                right_part = ' ' * border_right_chars
                            faded_art.append(left_part + middle_part + right_part)
                        else:
                            faded_art.append(left_part + middle_part + right_part)
                    else:
                        faded_art.append(line)
            
            print(colorize_text('\n'.join(faded_art), COLORS[-1]))
            time.sleep(frame_rate)

    def clear_screen():
        """Clear the terminal screen."""
        print("\033[H\033[J", end="", flush=True)

    def colorize_text(text, color):
        """Colorize the given text with the provided color."""
        return color + text + Style.RESET_ALL

    def display_rainbow_gradient(ascii_art, colors, duration=1, frame_rate=0.033):
        """Display the ASCII art with a rainbow gradient transition from top to bottom over 30 frames."""
        total_frames = 30
        frame_duration = duration / total_frames
        ascii_lines = ascii_art.split('\n')
        num_rows = len(ascii_lines)

        for frame in range(total_frames):
            clear_screen()
            gradient_art = []

            for i, line in enumerate(ascii_lines):
                # Calculate the color index based on both the row number and frame number
                color_index = int(((i / num_rows) + (frame / total_frames)) * len(colors)) % len(colors)
                line_color = colors[color_index]
                gradient_art.append(colorize_text(line, line_color))
        
            print('\n'.join(gradient_art))
            time.sleep(frame_duration)

        
    ascii_art = """
 /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\ 
( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )
 > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ < 
 /\_/\  ::::::::      :::     ::::    ::::  :::::::::: ::::::::  ::::    :::  /\_/\ 
( o.o ):+:    :+:   :+: :+:   +:+:+: :+:+:+ :+:       :+:    :+: :+:+:   :+: ( o.o )
 > ^ < +:+         +:+   +:+  +:+ +:+:+ +:+ +:+       +:+    +:+ :+:+:+  +:+  > ^ < 
 /\_/\ :#:        +#++:++#++: +#+  +:+  +#+ +#++:++#  +#+    +:+ +#+ +:+ +#+  /\_/\ 
( o.o )+#+   +#+# +#+     +#+ +#+       +#+ +#+       +#+    +#+ +#+  +#+#+# ( o.o )
 > ^ < #+#    #+# #+#     #+# #+#       #+# #+#       #+#    #+# #+#   #+#+#  > ^ < 
 /\_/\  ########  ###     ### ###       ### ########## ########  ###    ####  /\_/\ 
( o.o )                :::     ::::    :::  ::::::::  ::::    :::            ( o.o )
 > ^ <               :+: :+:   :+:+:   :+: :+:    :+: :+:+:   :+:             > ^ < 
 /\_/\              +:+   +:+  :+:+:+  +:+ +:+    +:+ :+:+:+  +:+             /\_/\ 
( o.o )            +#++:++#++: +#+ +:+ +#+ +#+    +:+ +#+ +:+ +#+            ( o.o )
 > ^ <             +#+     +#+ +#+  +#+#+# +#+    +#+ +#+  +#+#+#             > ^ < 
 /\_/\             #+#     #+# #+#   #+#+# #+#    #+# #+#   #+#+#             /\_/\ 
( o.o )            ###     ### ###    ####  ########  ###    ####            ( o.o )
 > ^ <                                                                        > ^ < 
 /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\  /\_/\ 
( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )( o.o )
 > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ <  > ^ < 
"""

    border_art = """\



        ::::::::      :::     ::::    ::::  :::::::::: ::::::::  ::::    :::
       :+:    :+:   :+: :+:   +:+:+: :+:+:+ :+:       :+:    :+: :+:+:   :+: 
       +:+         +:+   +:+  +:+ +:+:+ +:+ +:+       +:+    +:+ :+:+:+  +:+  
       :#:        +#++:++#++: +#+  +:+  +#+ +#++:++#  +#+    +:+ +#+ +:+ +#+  
       +#+   +#+# +#+     +#+ +#+       +#+ +#+       +#+    +#+ +#+  +#+#+# 
       #+#    #+# #+#     #+# #+#       #+# #+#       #+#    #+# #+#   #+#+#  
        ########  ###     ### ###       ### ########## ########  ###    #### 
                       :::     ::::    :::  ::::::::  ::::    :::            
                     :+: :+:   :+:+:   :+: :+:    :+: :+:+:   :+:             
                    +:+   +:+  :+:+:+  +:+ +:+    +:+ :+:+:+  +:+            
                   +#++:++#++: +#+ +:+ +#+ +#+    +:+ +#+ +:+ +#+            
                   +#+     +#+ +#+  +#+#+# +#+    +#+ +#+  +#+#+#             
                   #+#     #+# #+#   #+#+# #+#    #+# #+#   #+#+#             
                   ###     ### ###    ####  ########  ###    ####            \



"""

    # Phase 1: Initial animation
    animate_colors(ascii_art, COLORS)
    time.sleep(.1)  # Short pause before transitioning to fade effect
    
    # Phase 2: Rainbow gradient
    clear_screen()
    colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.BLUE, Fore.MAGENTA]
    display_rainbow_gradient(ascii_art, colors)

    # Phase 3: Fade out specified borders
    fade_out_borders(ascii_art, border_art, duration=.5, frame_rate=0.033)
    
    # Phase 4: Transition to green with standing border
    #clear_screen()
    #print(colorize_text(border_art, GREEN))
    #time.sleep(1)  # Pause to show green transition

    # Phase 5: Rainbow gradient
    clear_screen()
    display_rainbow_gradient(border_art, COLORS, duration=1, frame_rate=0.033)

# Function to handle errors
def handle_error(e):
    print(f"Error: {e}")
    sys.exit(1)

def game_1():

    # Game Settings
    WIDTH, HEIGHT = 800, 600
    FPS = 60
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    RED = (255, 0, 0)
    YELLOW = (255, 255, 0)

    # Initial speeds
    CLOUD_INITIAL_SPEED = 10  # Adjusted to 1/10th of original speed
    OBSTACLE_INITIAL_SPEED = 500  #1x speed
    POWERUP_INITIAL_SPEED = 250  # Halved speed

    # Accelerations
    CLOUD_ACCELERATION = 5
    OBSTACLE_ACCELERATION = 10
    POWERUP_ACCELERATION = 5

    # Flash and horizon settings
    FLASH_DURATION = 5000  # in milliseconds
    HORIZON_SPEED = 50

    # Load background images
    background_images = [pygame.image.load(f'images/background{i}.png') for i in range(5)]
    overlay_image = pygame.image.load('images/overlay.png')  # Load overlay image

    # Load PNG sequences for animations
    def load_images(folder, filenames):
        return [pygame.image.load(os.path.join(folder, filename)) for filename in filenames]

    # Load PNG sequences and enlarge by 2x
    def load_and_resize_images(folder, filenames, scale=1):
        images = []
        for filename in filenames:
            img = pygame.image.load(os.path.join(folder, filename))
            img = pygame.transform.scale(img, (img.get_width() * scale, img.get_height() * scale))
            images.append(img)
        return images

    # Load PNG sequences
    idle_images = load_images('images', ['idle_0.png', 'idle_1.png'])
    walk_images = load_images('images', ['walk_0.png', 'walk_1.png', 'walk_2.png', 'walk_3.png'])
    fall_images = load_images('images', ['fall_0.png', 'fall_1.png', 'fall_2.png', 'fall_3.png', 'fall_4.png', 'fall_5.png', 'fall_6.png', 'fall_7.png'])
    die_images = load_images('images', ['die_0.png', 'die_1.png'])
    roll_images = load_images('images', ['roll_0.png', 'roll_1.png', 'roll_2.png', 'roll_3.png', 'roll_4.png', 'roll_5.png', 'roll_6.png', 'roll_7.png', 'roll_8.png', 'roll_9.png'])

    # Load specific images for clouds, obstacles, and power-ups
    cloud_images = load_images('images', ['cloud_0.png', 'cloud_1.png'])
    obstacle_images = load_images('images', ['obstacle_0.png', 'obstacle_1.png', 'obstacle_2.png', 'obstacle_3.png', 'obstacle_4.png'])
    power_up_images = load_images('images', ['powerup_0.png', 'powerup_1.png', 'powerup_2.png', 'powerup_3.png', 'powerup_4.png', 'powerup_5.png', 'powerup_6.png', 'powerup_7.png', 'powerup_8.png', 'powerup_9.png', 'powerup_10.png'])

    # Define ParallaxBackground, Score, Cloud, Obstacle, PowerUp, and Runner classes
    class ParallaxBackground:
        def __init__(self, canvas, background_images, overlay_image, cloud_images, background_speed, overlay_speed, cloud_speed):
            self.canvas = canvas
            self.background_images = background_images
            self.overlay_image = overlay_image
            self.cloud_images = cloud_images
            self.background_speed = background_speed
            self.overlay_speed = overlay_speed
            self.cloud_speed = cloud_speed

            self.background_x = 0
            self.overlay_x = 0
            self.cloud_x = 0

            self.clouds = self._generate_clouds()

        def _generate_clouds(self):
            clouds = []
            for _ in range(5):  # Example: 5 clouds
                x = random.randint(0, WIDTH)
                y = random.randint(0, HEIGHT // 2)  # Clouds are usually in the upper part of the screen
                cloud_image = random.choice(self.cloud_images)
                clouds.append({'rect': pygame.Rect(x, y, cloud_image.get_width(), cloud_image.get_height()), 'image': cloud_image})
            return clouds

        def update(self, delta_time):
            self.background_x -= self.background_speed * delta_time
            if self.background_x <= -WIDTH:
                self.background_x = 0

            self.overlay_x -= self.overlay_speed * delta_time
            if self.overlay_x <= -WIDTH:
                self.overlay_x = 0

            self.cloud_x -= self.cloud_speed * delta_time
            if self.cloud_x <= -self.cloud_images[0].get_width():
                self.cloud_x = 0
                self.clouds = self._generate_clouds()

        def draw(self):
            # Draw the background
            self.canvas.blit(self.background_images[0], (self.background_x, 0))
            self.canvas.blit(self.background_images[0], (self.background_x + WIDTH, 0))

            # Draw the clouds
            for cloud in self.clouds:
                self.canvas.blit(cloud['image'], cloud['rect'].topleft)

            # Draw the overlay
            self.canvas.blit(self.overlay_image, (self.overlay_x, 0))
            self.canvas.blit(self.overlay_image, (self.overlay_x + WIDTH, 0))

    class Score:
        def __init__(self):
            self.score = 69420
            self.font = pygame.font.SysFont(None, 36)
            self.start_time = time.time()  # Initialize start time

        def increment(self, amount):
            self.score += amount

        def update(self):
            # Calculate elapsed time
            elapsed_time = time.time() - self.start_time
            # Increment score based on elapsed time (e.g., +1 point per second)
            self.score = int(elapsed_time)

        def draw(self, canvas):
            score_surface = self.font.render(f"Score: {self.score}", True, WHITE)
            canvas.blit(score_surface, (10, 10))  # Draw score in the top-left corner

    class Cloud:
        def __init__(self, canvas, sprite_pos, width):
            self.canvas = canvas
            self.sprite_pos = sprite_pos
            self.x_pos = width
            self.y_pos = random.randint(50, HEIGHT - 50)  # Updated min Y position
            self.width = 200  # Assumed width
            self.height = 200  # Assumed height
            self.remove = False
            self.speed = CLOUD_INITIAL_SPEED
            self.acceleration = CLOUD_ACCELERATION
            self.frame_index = 0
            self.frame_counter = 0
            self.frame_delay = 200  # milliseconds, default delay for cloud frames
            self.offset_x = 0
            self.offset_y = 0

        def update(self, delta_time):
            self.speed += self.acceleration * delta_time
            self.x_pos -= self.speed
            if self.x_pos + self.width < 0:
                self.remove = True

            # Update animation frame
            self.frame_counter += pygame.time.get_ticks() / 1000
            if self.frame_counter > self.frame_delay:
                self.frame_index = (self.frame_index + 1) % len(cloud_images)
                self.frame_counter = 0

        def draw(self):
            frame = cloud_images[self.frame_index]
            self.canvas.blit(frame, (self.x_pos, self.y_pos))

        def get_rect(self):
            return pygame.Rect(self.x_pos + self.offset_x, self.y_pos + self.offset_y, self.width, self.height)

    class Obstacle:
        def __init__(self, canvas, obstacle_type, sprite_pos, dimensions, current_speed, width):
            self.canvas = canvas
            self.obstacle_type = obstacle_type
            self.sprite_pos = sprite_pos
            self.x_pos = dimensions['WIDTH']
            self.y_pos = random.randint(HEIGHT // 2 - 64, HEIGHT - 32)  # Adjusted minimum Y position
            self.width = width  # Width of the obstacle
            self.height = 32  # Height of the obstacle
            self.hitbox_size = 48  # Fixed size for the hitbox
            self.remove = False
            self.speed = current_speed
            self.acceleration = OBSTACLE_ACCELERATION
            self.frame_index = 0
            self.frame_counter = 0
            self.frame_delay = 200  # milliseconds, default delay for obstacle frames
            self.offset_x = 0
            self.offset_y = 0

        def update(self, delta_time):
            self.speed += self.acceleration * delta_time
            self.x_pos -= self.speed * delta_time
            if self.x_pos + self.width < 0:
                self.remove = True

            # Update animation frame
            self.frame_counter += pygame.time.get_ticks() / 1000
            if self.frame_counter > self.frame_delay:
                self.frame_index = (self.frame_index + 1) % len(obstacle_images)
                self.frame_counter = 0

        def draw(self):
            frame = obstacle_images[self.frame_index]
            self.canvas.blit(frame, (self.x_pos, self.y_pos))

        def get_rect(self):
            # Center the 48x48 hitbox on the sprite
            center_x = self.x_pos + self.width // 2
            center_y = self.y_pos + self.height // 2
            hitbox_x = center_x - self.hitbox_size // 2
            hitbox_y = center_y - self.hitbox_size // 2
            return pygame.Rect(hitbox_x + self.offset_x, hitbox_y + self.offset_y, self.hitbox_size, self.hitbox_size)

    class PowerUp:
        def __init__(self, canvas_ctx, sprite_pos, dimensions):
            self.canvas_ctx = canvas_ctx
            self.sprite_pos = sprite_pos
            self.x_pos = dimensions['WIDTH']
            self.y_pos = random.randint(runner_y_pos, runner_y_pos + 50)  # Updated min Y position
            self.width = 20
            self.height = 20
            self.hitbox_size = 48  # Fixed size for the hitbox
            self.remove = False
            self.speed = POWERUP_INITIAL_SPEED
            self.acceleration = POWERUP_ACCELERATION
            self.frame_index = 0
            self.frame_counter = 0
            self.frame_delay = 200  # milliseconds, default delay for power-up frames
            self.offset_x = 0
            self.offset_y = 0

        def update(self, delta_time):
            self.speed += self.acceleration * delta_time
            self.x_pos -= self.speed * delta_time
            if self.x_pos + self.width < 0:
                self.remove = True

            # Update animation frame
            self.frame_counter += pygame.time.get_ticks() / 1000
            if self.frame_counter > self.frame_delay:
                self.frame_index = (self.frame_index + 1) % len(power_up_images)
                self.frame_counter = 0

        def draw(self):
            frame = power_up_images[self.frame_index]
            self.canvas_ctx.blit(frame, (self.x_pos, self.y_pos))

        def get_rect(self):
            # Center the 48x48 hitbox on the sprite
            center_x = self.x_pos + self.width // 2
            center_y = self.y_pos + self.height // 2
            hitbox_x = center_x - self.hitbox_size // 2
            hitbox_y = center_y - self.hitbox_size // 2
            return pygame.Rect(hitbox_x + self.offset_x, hitbox_y + self.offset_y, self.hitbox_size, self.hitbox_size)

    class Runner:
        def __init__(self, canvas):
            self.canvas = canvas
            self.x_pos = WIDTH // 4
            self.y_pos = HEIGHT - 64  # Adjust as needed
            self.width = 20
            self.height = 20
            self.hitbox_size = 48  # Fixed size for the hitbox
            self.current_animation = 'idle'
            self.frame_index = 0
            self.frame_counter = 0
            self.frame_delay = 100  # milliseconds, default delay for frame updates
            self.speed = 200
            self.sprites = {
                'idle': idle_images,
                'walk': walk_images,
                'fall': fall_images,
                'die': die_images,
                'roll': roll_images
            }
            self.is_jumping = False
            self.jump_height = 15
            self.gravity = 1
            self.velocity = 0
            self.jump_count = 0
            self.max_jumps = 2
            self.offset_x = 0
            self.offset_y = 0

            # Animation timings
            self.idle_frame_times = [1000, 100]  # Time in milliseconds for each frame
            self.current_frame_time_index = 0
            self.current_frame_time = pygame.time.get_ticks()

        def update(self, keys, delta_time):
            current_time = pygame.time.get_ticks()

            if keys[pygame.K_LEFT]:
                self.x_pos -= self.speed * delta_time
                self.current_animation = 'walk'
            if keys[pygame.K_RIGHT]:
                self.x_pos += self.speed * delta_time
                self.current_animation = 'walk'
            if not keys[pygame.K_LEFT] and not keys[pygame.K_RIGHT]:
                self.current_animation = 'idle'
                if current_time - self.current_frame_time >= self.idle_frame_times[self.current_frame_time_index]:
                    # Switch to the next frame
                    self.frame_index = (self.frame_index + 1) % len(idle_images)
                    self.current_frame_time = current_time
                    self.current_frame_time_index = (self.current_frame_time_index + 1) % len(self.idle_frame_times)
                    
            if (keys[pygame.K_SPACE] or keys[pygame.K_UP]) and self.jump_count < self.max_jumps:
                self.current_animation = 'fall'
                if not self.is_jumping:
                    self.velocity = -self.jump_height
                    self.is_jumping = True
                    self.jump_count += 1
            else:
                self.current_animation = 'roll'
            
            if self.is_jumping:
                self.velocity += self.gravity
                self.y_pos += self.velocity
                if self.y_pos >= HEIGHT - 128:
                    self.y_pos = HEIGHT - 128
                    self.is_jumping = False
                    self.velocity = 0
                    self.jump_count = 0  # Reset jump count when on the ground

            # Update animation frame
            if self.current_animation in self.sprites:
                frames = self.sprites[self.current_animation]
                if self.current_animation == 'idle':
                    # The idle animation is handled with custom timing
                    pass
                else:
                    # Handle other animations (walk, fall, die, roll) normally
                    self.frame_counter += pygame.time.get_ticks() / 1000
                    if self.frame_counter > self.frame_delay:
                        self.frame_index = (self.frame_index + 1) % len(frames)
                        self.frame_counter = 0

        def draw(self):
            if self.current_animation not in self.sprites:
                raise ValueError(f"Invalid animation state: {self.current_animation}")
            frames = self.sprites[self.current_animation]
            if not frames:
                raise ValueError(f"No frames available for animation: {self.current_animation}")
            if self.frame_index >= len(frames):
                self.frame_index = len(frames) - 1  # Fix frame index to be within range
            frame = frames[self.frame_index]
            self.canvas.blit(frame, (self.x_pos + self.offset_x, self.y_pos + self.offset_y))

        def get_rect(self):
            # Center the 48x48 hitbox on the sprite
            center_x = self.x_pos + self.width // 2
            center_y = self.y_pos + self.height // 2
            hitbox_x = center_x - self.hitbox_size // 2
            hitbox_y = center_y - self.hitbox_size // 2
            return pygame.Rect(hitbox_x + self.offset_x, hitbox_y + self.offset_y, self.hitbox_size, self.hitbox_size)

    class DistanceMeter:
        def __init__(self, settings):
            self.settings = settings
            self.distance = 0

        def update(self, delta_time, speed):
            self.distance += speed * delta_time

            if self.distance >= self.settings['ACHIEVEMENT_DISTANCE']:
                self.flash()

        def flash(self):
            # Implement the flash effect here
            pass

        def draw(self, canvas):
            # Implement drawing the distance meter
            pass

    class HorizonLine:
        def __init__(self, canvas, sprite_pos):
            self.canvas = canvas
            self.sprite_pos = sprite_pos
            self.x_pos = 0
            self.y_pos = HEIGHT - 64
            self.width = WIDTH
            self.height = 10

        def update(self, delta_time, speed):
            self.x_pos -= speed * delta_time
            if self.x_pos + self.width < 0:
                self.x_pos = 0

        def draw(self):
            pygame.draw.rect(self.canvas, WHITE, pygame.Rect(self.x_pos, self.y_pos, self.width, self.height))

    class NightMode:
        def __init__(self, canvas, sprite_pos, width):
            self.canvas = canvas
            self.sprite_pos = sprite_pos
            self.x_pos = 0
            self.y_pos = 0
            self.width = width
            self.height = HEIGHT
            self.alpha = 0

        def update(self, delta_time):
            # Gradually increase darkness
            self.alpha = min(self.alpha + 1, 255)
            overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, self.alpha))
            self.canvas.blit(overlay, (self.x_pos, self.y_pos))

        def draw(self):
            pass

    def main():
        pygame.init()
        canvas = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('The Game')
        clock = pygame.time.Clock()

        runner = Runner(canvas)
        parallax_background = ParallaxBackground(
            canvas, 
            background_images, 
            overlay_image, 
            cloud_images, 
            background_speed=100, 
            overlay_speed=50, 
            cloud_speed=30
        )    

        clouds = []  # Example list of clouds
        obstacles = []  # Example list of obstacles
        power_ups = []  # Example list of power-ups
        distance_meter = DistanceMeter({'ACHIEVEMENT_DISTANCE': 1000, 'FLASH_DURATION': FLASH_DURATION})
        horizon_line = HorizonLine(canvas, {'x': 0, 'y': 0})
        night_mode = NightMode(canvas, {'x': 0, 'y': 0}, WIDTH)
        score = Score()

        # Timers
        cloud_timer = pygame.time.get_ticks()
        obstacle_timer = pygame.time.get_ticks()
        power_up_timer = pygame.time.get_ticks()

        running = True
        while running:
            delta_time = clock.tick(FPS) / 1000  # Time passed since the last frame in seconds
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key in [pygame.K_ESCAPE, pygame.K_q]):
                    running = False

            keys = pygame.key.get_pressed()

            # Update game objects
            runner.update(keys, delta_time)
            parallax_background.update(delta_time)

            # Obstacle Timer Logic
            if pygame.time.get_ticks() - obstacle_timer > random.uniform(0.2, 2.0) * 1000:  # Random delay between 0.2 and 2 seconds
                obstacles.append(Obstacle(canvas, 'type1', {'x': 0, 'y': 0}, {'WIDTH': WIDTH, 'HEIGHT': HEIGHT}, OBSTACLE_INITIAL_SPEED, WIDTH))
                obstacle_timer = pygame.time.get_ticks()

            for obstacle in obstacles:
                obstacle.update(delta_time)
                if obstacle.remove:
                    obstacles.remove(obstacle)

            # Power-Up Timer Logic
            if pygame.time.get_ticks() - power_up_timer > 10000:  # Every 10 seconds
                # Pass the runner's y position to the power-up
                power_ups.append(PowerUp(canvas, {'x': 0, 'y': 0}, {'WIDTH': WIDTH, 'HEIGHT': HEIGHT}, runner.y_pos))
                power_up_timer = pygame.time.get_ticks()

            for power_up in power_ups:
                power_up.update(delta_time)
                if power_up.remove:
                    power_ups.remove(power_up)
            # Check if the runner has walked off the left side of the screen
            if runner.x_pos + runner.width < 0:
                print("Well, well, well...So you found my first key...")
                running = False

            # Collision Detection
            runner_rect = runner.get_rect()
            for obstacle in obstacles:
                if runner_rect.colliderect(obstacle.get_rect()):
                    print("Collision detected with obstacle!")
                    running = False  # End the game

            for power_up in power_ups:
                if runner_rect.colliderect(power_up.get_rect()):
                    print("Collision detected with power-up!")
                    power_up.remove = True  # Mark power-up for removal
            if runner.x_pos < -runner.width:
                glitch_effect(canvas, "GOING BACKWARDS WAS THE ONLY SOLUTION. WELL PLAYED")
                running = False  # End the game loop

            # Draw everything
            canvas.fill(BLACK)
            parallax_background.draw()  # Draw parallax background
            horizon_line.draw()
            for obstacle in obstacles:
                obstacle.draw()
            for power_up in power_ups:
                power_up.draw()
            runner.draw()
            night_mode.draw()
            score.draw(canvas)  # Draw the score on top

            pygame.display.flip()

        pygame.quit()

    def glitch_effect(canvas, message):
        # Save the original surface
        original_surface = canvas.copy()
    
        # Define glitch parameters
        glitch_duration = 3000  # 1 second in milliseconds
        start_time = pygame.time.get_ticks()
    
        while pygame.time.get_ticks() - start_time < glitch_duration:
            # Clear the canvas
            canvas.fill(BLACK)
        
            # Pixelation effect
            for y in range(0, HEIGHT, 8):
                for x in range(0, WIDTH, 8):
                    # Choose a random 8x8 block from the original surface
                    block_x = random.randint(0, WIDTH - 8)
                    block_y = random.randint(0, HEIGHT - 8)
                    canvas.blit(original_surface, (x, y), (block_x, block_y, 8, 8))
        
            # Color shift effect
            for _ in range(100):  # Number of color shift blocks
                x = random.randint(0, WIDTH - 1)
                y = random.randint(0, HEIGHT - 1)
                w = random.randint(1, 10)
                h = random.randint(1, 10)
                color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                pygame.draw.rect(canvas, color, (x, y, w, h))
        
            # Screen tearing effect
            tear_y = random.randint(0, HEIGHT - 1)
            canvas.blit(original_surface, (0, tear_y), (0, 0, WIDTH, tear_y))
            canvas.blit(original_surface, (0, tear_y), (0, tear_y + 1, WIDTH, HEIGHT - tear_y))
        
            # Draw the message
            font = pygame.font.Font(None, 36)
            text_surface = font.render(message, True, (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
            canvas.blit(text_surface, (WIDTH // 2 - text_surface.get_width() // 2, HEIGHT // 2 - text_surface.get_height() // 2))
        
            # Update display
            pygame.display.flip()
        
            # Small delay to control frame rate
            pygame.time.delay(30)  # About 30 FPS

        # Restore the original surface
        canvas.blit(original_surface, (0, 0))
        pygame.display.flip()

    main() 

def game_2():
    # Welcome Player
    print('Welcome to the game Oregon Trail ')

    # Asking name
    player_name = input('What is your name: ')
    while True:
        if len(player_name) > 1:
            print(f"{player_name}? It is a good name.")
            break
        elif len(player_name) == 1:
            player_name_choice = input(f"{player_name}? Are you kidding me? Only one letter?(y/n): ").lower()
            if player_name_choice in ['y', 'yes']:
                print("Ok...")
                break
            else:
                player_name = input('What is your name: ')
        else:
            print("You did not type anything, try again")
            player_name = input('What is your name: ')

    if player_name == 'Meriwether Lewis':
        year_set = 1803
        mode_choice = 'impossible'
    else:
        while True:
            year_set = input('Enter a year whatever you like: ')
            if year_set.isdigit():
                year_set = int(year_set)
                break
            print('Error, please try again!')
        print('Which mode do you want to play?')
        while True:
            mode_choice = input('(easy, normal, hard, impossible, customize): ').lower()
            if mode_choice in ['easy', 'normal', 'hard', 'impossible']:
                if mode_choice == 'easy':
                    food_num = 1000
                    health_num = 10
                elif mode_choice == 'normal':
                    food_num = 500
                    health_num = 5
                elif mode_choice == 'hard':
                    food_num = 300
                    health_num = 4
                else:  # impossible
                    food_num = 150
                    health_num = 3
                break
            elif mode_choice == 'customize':
                while True:
                    food_num = input('How much food do you want: ')
                    if food_num.isdigit():
                        food_num = int(food_num)
                        break
                    print('Error, please try again!')
                while True:
                    health_num = input('How much health do you want: ')
                    if health_num.isdigit():
                        health_num = int(health_num)
                        break
                    print('Error, please try again!')
                break
            else:
                print("Bad input, try again!")

    # Other basic starting value setting
    player_move_distance = 0
    month_num = 3
    days_pass = 1
    total_days = 0
    MONTHS_WITH_31_DAYS = [1, 3, 5, 7, 8, 10, 12]
    random_result = 0
    health_d1 = random.randint(1, 31)
    health_d2 = random.randint(1, 31)
    acident_appear = random.randint(1, 30)
    travel_total_num = 0
    rest_total_num = 0
    hunt_total_num = 0
    status_total_num = 0
    month_appear = 'March'

    # Add days function
    def add_days(min, max):
        global days_pass, month_num, random_result, food_num, health_num, total_days, health_d1, health_d2, acident_appear
        random_result = random.randint(min, max)
        print('Now', random_result, "days passed..")
        days_pass_min = days_pass
        check_big = days_pass + random_result

        # Accident
        if acident_appear >= days_pass and acident_appear <= check_big:
            a_number = random.randint(1, 3)
            a_health_num = random.randint(1, 2)
            if a_number == 1:
                print('During this time, you crossed a river.')
            elif a_number == 2:
                print('During this time, you had a dysentery.')
            elif a_number == 3:
                print('During this time, you saw a beautiful girl and had a good time with her.')
            random_result2_food = random.randint(1, 10)
            random_result2_day = random.randint(1, 10)
            print('As a result, you eat ' + str(random_result2_food) + ' lbs extra food.')
            print('It also took up extra ' + str(random_result2_day) + ' days.')
            if a_health_num == 1:
                print('And you also lose 1 health')
                health_num -= 1
            food_num -= random_result2_food + random_result2_day * 5
            days_pass += random_result2_day
            total_days += random_result2_day

        # Health decrease randomly
        if health_d1 >= days_pass_min and health_d1 <= check_big:
            health_num -= 1
            print('Unfortunately, you lose 1 health during this time.')
        if health_d2 >= days_pass_min and health_d2 <= check_big:
            health_num -= 1
            print('Unfortunately, you lose 1 health during this time.')

        days_pass += random_result
        total_days += random_result
        food_num -= random_result * 5

        if days_pass > 30:
            if month_num not in MONTHS_WITH_31_DAYS:
                days_pass -= 30
            else:
                days_pass -= 31
            month_num += 1
            health_d1 = random.randint(1, 30)
            health_d2 = random.randint(1, 30)
            acident_appear = random.randint(1, 30)

    # Travel function
    def travle1(movedistance):
        global travel_total_num
        add_days(3, 7)
        movedistance += random.randint(30, 60)
        travel_total_num += 1
        return movedistance

    # Rest function
    def rest(health):
        global rest_total_num
        add_days(2, 5)
        health += 1
        rest_total_num += 1
        return health

    # Hunt function
    def hunt(hunting_food):
        global hunt_total_num
        add_days(2, 5)
        hunting_food += 100
        print('Gain: 100 lbs food')
        hunt_total_num += 1
        return hunting_food

    # Month appearance function
    def month_appear_fun():
        global month_appear
        months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
        month_appear = months[month_num - 1]
        return month_appear

    # Loading part
    print('--------------------------------------')
    print('Now Loading...')
    time.sleep(0.5)
    print('Now loading the player setting...')
    time.sleep(2)
    print('Successfully!')
    time.sleep(0.5)
    print('Now loading the game setting...')
    time.sleep(2)
    print('Successfully!')
    time.sleep(0.5)
    print('Preparing the trip for Oregon...')
    time.sleep(2)
    print('Successfully!')
    time.sleep(0.5)
    print('Now game is ready!')
    print('--------------------------------------')
    print('Attention:')
    print('We will be recreating Oregon Trail! The goal is to travel from NYC to')
    print('Oregon (2000 miles) by Dec 31st. However, the trail is arduous. Each')
    print('day costs you food and health. You can hunt and rest, but you have to')
    print('get there before winter. If confused, type help. GOOD LUCK!')
    print('--------------------------------------')

    # Main game loop
    while player_move_distance < 2000 and food_num > 0 and health_num > 0 and month_num < 13:
        month_appear_fun()
        if food_num <= 50:
            print(f'Warning! You only have {food_num} lbs food now.')
            print('You need to hunt now.')
        if health_num <= 2:
            print(f'Warning! You only have {health_num} health now.')
            print('You need to rest now.')
        print(f'Now {month_appear} {days_pass}th')
        print(f'Food: {food_num} lbs')
        print(f'Health: {health_num}')
        print(f'Distance traveled: {player_move_distance} miles')
        print(f'Total days passed: {total_days} days')
        print('What do you want to do?')
        action = input('(travel, rest, hunt, status): ').lower()

        if action == 'travel':
            player_move_distance = travle1(player_move_distance)
        elif action == 'rest':
            health_num = rest(health_num)
        elif action == 'hunt':
            food_num = hunt(food_num)
        elif action == 'status':
            print(f'Travel: {travel_total_num} times')
            print(f'Rest: {rest_total_num} times')
            print(f'Hunt: {hunt_total_num} times')
            print(f'Status: {status_total_num} times')
            status_total_num += 1
        else:
            print("Invalid action, please try again.")

        # Check for game over conditions
        if player_move_distance >= 2000:
            print('Congratulations! You have reached Oregon!')
            break
        elif food_num <= 0:
            print('You have run out of food. Game Over!')
            break
        elif health_num <= 0:
            print('Your health has run out. Game Over!')
            break
        elif month_num == 12 and days_pass >= 31:
            print('You did not reach Oregon before the end of the year. Game Over!')
            break

    # End of game message
    print('Game Over!')
    print(f'You traveled {player_move_distance} miles.')
    print(f'You had {food_num} lbs of food left.')
    print(f'Your health was at {health_num}.')
    print(f'Total days on the trail: {total_days} days.')

def game_3():
    import heapq
    from collections import defaultdict

    # Initialize Pygame
    pygame.init()
    pygame.font.init()
    clock = pygame.time.Clock()

    # Game constants
    PLAYER_SIZE = 20
    PLAYER_SPEED = 5
    WIDTH, HEIGHT = 800, 600
    BLACK = (0, 0, 0)
    BLUE = (0, 0, 255)
    YELLOW = (255, 255, 0)
    RED = (255, 0, 0)
    WHITE = (255, 255, 255)

    # Setup the window
    WINDOW = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Tron AI")
    
    # Game variables should be defined here if not already globally defined
    global trails, score, game_over, difficulty, powerups, player1_pos, player2_pos, player1_dir, player2_dir
    trails = [[], []]
    score = [0, 0]
    game_over = False
    difficulty = 1
    powerups = []
    font = pygame.font.Font(None, 36)

    # Ensure these are defined before main() is called
    player1_pos = None  # Will be properly set in main or another init function
    player2_pos = None  # Same as above
    player1_dir = None  # Will be initialized in main
    player2_dir = None  # Will be initialized in main

    # AStarNode class definition
    class AStarNode:
        def __init__(self, pos, g, h, parent=None):
            self.pos = pos
            self.g = g
            self.h = h
            self.f = g + h
            self.parent = parent

        def __lt__(self, other):
            return self.f < other.f

    # TronAI class definition
    class TronAI:
        def __init__(self, width, height):
            self.width = width
            self.height = height
            self.difficulty = 1
            self.grid = [[0 for _ in range(height)] for _ in range(width)]
            self.open_list = []
            self.closed_set = set()

    def update_difficulty(self):
        self.difficulty += 0.5  # Increase difficulty each time player wins

    def heuristic(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])  # Manhattan distance

    def get_neighbors(self, pos):
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        neighbors = []
        for dx, dy in directions:
            new_pos = (pos[0] + dx * PLAYER_SIZE, pos[1] + dy * PLAYER_SIZE)
            if 0 <= new_pos[0] < self.width and 0 <= new_pos[1] < self.height and self.grid[new_pos[0]][new_pos[1]] == 0:
                neighbors.append(new_pos)
        return neighbors

    def a_star_search(self, start, goal):
        start_node = AStarNode(start, 0, self.heuristic(start, goal))
        heapq.heappush(self.open_list, start_node)
        self.closed_set.clear()

        while self.open_list:
            current_node = heapq.heappop(self.open_list)

            if current_node.pos == goal:
                path = []
                while current_node:
                    path.append(current_node.pos)
                    current_node = current_node.parent
                return path[::-1]  # Return reversed path

            self.closed_set.add(current_node.pos)

            for neighbor_pos in self.get_neighbors(current_node.pos):
                if neighbor_pos in self.closed_set:
                    continue

                neighbor_node = AStarNode(neighbor_pos, current_node.g + 1, self.heuristic(neighbor_pos, goal), current_node)

                if neighbor_node not in self.open_list:
                    heapq.heappush(self.open_list, neighbor_node)
                else:
                    # If this node is already in open_list but with a higher cost, update it
                    idx = self.open_list.index(neighbor_node)
                    if self.open_list[idx].g > neighbor_node.g:
                        self.open_list[idx] = neighbor_node
                        heapq.heapify(self.open_list)

        return None  # No path found

    def update_grid(self, trails):
        for row in self.grid:
            row[:] = [0] * self.height  # Reset grid
        for trail in trails:
            for x, y in trail:
                if 0 <= x < self.width and 0 <= y < self.height:
                    self.grid[int(x)][int(y)] = 1

    def move(self, current_pos, player_trail, opponent_trail):
        self.update_grid([player_trail, opponent_trail])
        
        # Here we set a goal that's far from the player to encourage long survival
        goal = (self.width - current_pos[0], self.height - current_pos[1]) if random.random() < 0.5 else (0, 0)
        
        # With increased difficulty, AI might choose to cut off player or go for a powerup
        if random.random() < self.difficulty / 10:
            # Try to cut off player or go for strategic advantage
            goal = self.strategic_goal(current_pos, player_trail[-1])

        path = self.a_star_search(current_pos, goal)
        if path and len(path) > 1:
            return [path[1][0] - current_pos[0], path[1][1] - current_pos[1]]
        else:
            # If no path found or only current position, make a random safe move
            safe_moves = self.get_neighbors(current_pos)
            if safe_moves:
                return [random.choice(safe_moves)[0] - current_pos[0], random.choice(safe_moves)[1] - current_pos[1]]
            else:
                # If no safe moves, we're trapped, so just don't move or move into self to end game
                return [0, 0]  # or [-current_dir[0], -current_dir[1]] to move into self

    def strategic_goal(self, ai_pos, player_pos):
        # This method should implement strategic decisions like cutting off the player,
        # going for power-ups, or trapping the player. Here's a simple version:
        # 1. If close to player, try to cut off
        if abs(ai_pos[0] - player_pos[0]) + abs(ai_pos[1] - player_pos[1]) < 100:
            return (player_pos[0] + (ai_pos[0] - player_pos[0]) * 2, 
                    player_pos[1] + (ai_pos[1] - player_pos[1]) * 2)
        # 2. Otherwise, default to a far corner or edge for survival
        return random.choice([(0, 0), (self.width-1, self.height-1), (0, self.height-1), (self.width-1, 0)])

    def ai_move(difficulty):
        global player2_dir, player2_pos, trails
    
        # Assuming player2_pos is the AI's position and player1_pos for the player's last position
        new_dir = ai.move(player2_pos, trails[1], trails[0])  # trails[1] is assumed to be AI's trail
    
        # Normalize direction if diagonal movement is not allowed
        if abs(new_dir[0]) + abs(new_dir[1]) > 1:
            new_dir = [1 if new_dir[0] > 0 else (-1 if new_dir[0] < 0 else 0),
                       1 if new_dir[1] > 0 else (-1 if new_dir[1] < 0 else 0)]
    
        player2_dir = new_dir
 

    def customization_menu(font):
        running = True
        selected_option = None
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        running = False
                    elif event.key == pygame.K_1:
                        selected_option = "player1_color"
                    elif event.key == pygame.K_2:
                        selected_option = "player2_color"
                    elif event.key == pygame.K_3:
                        # Option to start the game directly from here or handle it as needed
                        running = False
                        selected_option = "start_game"

            WINDOW.fill(BLACK)
            title = font.render("Customize Your Light Cycle", True, WHITE)
            WINDOW.blit(title, (WIDTH // 2 - 150, 50))
        
            option1 = font.render("1. Choose Player 1 Color", True, WHITE)
            option2 = font.render("2. Choose Player 2 Color", True, WHITE)
            option3 = font.render("3. Start Game", True, WHITE)
            WINDOW.blit(option1, (WIDTH // 2 - 100, 150))
            WINDOW.blit(option2, (WIDTH // 2 - 100, 200))
            WINDOW.blit(option3, (WIDTH // 2 - 100, 250))
        
            pygame.display.flip()
        
            # Return default customization for now
            return {"player1_color": WHITE, "player2_color": BLUE}

        # Here you might want to implement color selection or directly return the selected option
        if selected_option == "player1_color":
            return {"player1_color": choose_color(), "player2_color": BLUE}  # Assuming BLUE for player 2 or implement choose_color for both
        elif selected_option == "player2_color":
            return {"player1_color": WHITE, "player2_color": choose_color()}
        elif selected_option == "start_game":
            return {"player1_color": WHITE, "player2_color": BLUE}  # Default colors
        else:
            return {"player1_color": WHITE, "player2_color": BLUE} 

    def choose_color():
        colors = {
            'Red': (255, 0, 0),
            'Green': (0, 255, 0),
            'Blue': (0, 0, 255),
            'Yellow': (255, 255, 0),
            'Cyan': (0, 255, 255),
            'Magenta': (255, 0, 255),
            'White': (255, 255, 255),
            'Black': (0, 0, 0)
        }
    
        running = True
        selected_color = 'White'  # Default selection
    
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        return colors[selected_color]
                    elif event.key == pygame.K_UP or event.key == pygame.K_DOWN:
                        # Assuming the first color listed is 'Red' and the last is 'Black'
                        color_keys = list(colors.keys())
                        current_index = color_keys.index(selected_color)
                        if event.key == pygame.K_UP:
                            next_index = (current_index - 1) % len(color_keys)
                        else:  # DOWN
                            next_index = (current_index + 1) % len(color_keys)
                        selected_color = color_keys[next_index]
                    elif event.key == pygame.K_ESCAPE:
                        running = False
        
            WINDOW.fill(BLACK)
            title = font.render("Choose a Color", True, WHITE)
            WINDOW.blit(title, (WIDTH // 2 - 75, 50))
        
            for i, (color_name, color_value) in enumerate(colors.items()):
                color_text = font.render(color_name, True, color_value if color_name == selected_color else WHITE)
                WINDOW.blit(color_text, (WIDTH // 2 - 50, 100 + i * 30))
        
            pygame.display.flip()

        # If the player exits without choosing, return white
        return colors['White']

    def move_player(pos, direction, speed):
        pos[0] += direction[0] * PLAYER_SPEED * speed
        pos[1] += direction[1] * PLAYER_SPEED * speed

    def ai_move(difficulty):
        # This is a placeholder for AI logic. 
        # The actual implementation would depend on how sophisticated you want the AI to be.
        # Here's a simple example where AI tries to avoid walls and its own trail:
        global player2_dir
    
        # Avoid walls
        if player2_pos[0] < PLAYER_SIZE or player2_pos[0] > WIDTH - PLAYER_SIZE:
            player2_dir[0] *= -1
        if player2_pos[1] < PLAYER_SIZE or player2_pos[1] > HEIGHT - PLAYER_SIZE:
            player2_dir[1] *= -1
    
        # Simple trail avoidance (this is very basic and might not work well in practice)
        for trail in trails[1]:
            if abs(trail[0] - player2_pos[0]) < PLAYER_SIZE and abs(trail[1] - player2_pos[1]) < PLAYER_SIZE:
                player2_dir = [random.choice([-1, 1]), random.choice([-1, 1])]
                break

    def apply_powerup(player, powerup):
        # Placeholder for powerup effects
        if powerup['type'] == 'speed':
            player['speed'] = 2  # Double speed for a short time, for example
        elif powerup['type'] == 'shield':
            player['shield'] = True

    def spawn_powerup():
        if len(powerups) < 3:
            powerup = {
                'pos': [random.randint(0, WIDTH), random.randint(0, HEIGHT)],
                'type': random.choice(['speed', 'shield'])
            }
            powerups.append(powerup)

    def check_collision(pos, trail):
        # Check if the position collides with any point in the trail or the boundaries
        if (pos[0] < 0 or pos[0] >= WIDTH or pos[1] < 0 or pos[1] >= HEIGHT):
            return True
        for point in trail:
            if abs(pos[0] - point[0]) < PLAYER_SIZE and abs(pos[1] - point[1]) < PLAYER_SIZE:
                return True
        return False

    def draw_game():
        WINDOW.fill(BLACK)
    
        # Draw trails
        for trail in trails:
            for point in trail:
                pygame.draw.rect(WINDOW, WHITE if trail == trails[0] else BLUE, (point[0], point[1], PLAYER_SIZE, PLAYER_SIZE))
    
        # Draw players (assuming you have sprites or just draw rectangles for now)
        pygame.draw.rect(WINDOW, WHITE, (player1_pos[0], player1_pos[1], PLAYER_SIZE, PLAYER_SIZE))
        pygame.draw.rect(WINDOW, BLUE, (player2_pos[0], player2_pos[1], PLAYER_SIZE, PLAYER_SIZE))
    
        # Draw power-ups
        for powerup in powerups:
            pygame.draw.circle(WINDOW, YELLOW, (int(powerup['pos'][0]), int(powerup['pos'][1])), 5)
    
        # Draw score
        score_text = font.render(f"Score: {score[0]} - {score[1]}", True, WHITE)
        WINDOW.blit(score_text, (10, 10))
    
        if game_over:
            game_over_text = font.render("Game Over! Press 'R' to restart.", True, RED)
            WINDOW.blit(game_over_text, (WIDTH // 2 - 150, HEIGHT // 2))
    
        pygame.display.flip()

    player1_sprite = pygame.image.load('images/ship.png')
    player2_sprite = pygame.image.load('images/ship2.png')

    # Apply customization (for now, just use the default colors)
    player1_sprite = pygame.transform.scale(player1_sprite, (PLAYER_SIZE, PLAYER_SIZE))
    player2_sprite = pygame.transform.scale(player2_sprite, (PLAYER_SIZE, PLAYER_SIZE))
    
    # Ensure these are defined before main() is called
    player1_pos = None  # Will be properly set in main or another init function
    player2_pos = None  # Same as above
    
    def main():
        global player1_pos, player2_pos, player1_dir, player2_dir, trails, score, game_over, difficulty
        customization = customization_menu(font)
                
        # Apply customization here, for example:
        player1_color = customization["player1_color"]
        player2_color = customization["player2_color"]

        # Initialize player positions here, before they're used
        player1_pos = [WIDTH // 4, HEIGHT // 2]
        player2_pos = [3 * WIDTH // 4, HEIGHT // 2]
        player1_dir = [0, 0]
        player2_dir = [0, 0]

        player1 = {'pos': player1_pos, 'dir': player1_dir, 'speed': 1, 'shield': False}
        player2 = {'pos': player2_pos, 'dir': player2_dir, 'speed': 1, 'shield': False}
        
        # Usage in your game loop:
        ai = TronAI(WIDTH, HEIGHT)

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                if game_over:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                        game_over = False
                        player1['pos'] = [WIDTH // 4, HEIGHT // 2]
                        player2['pos'] = [3 * WIDTH // 4, HEIGHT // 2]
                        player1['dir'] = player2['dir'] = [0, 0]
                        trails = [[], []]
                        score = [0, 0]
                        powerups.clear()
                        continue
                
                # Player 1 controls
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_w and player1['dir'][1] != 1: player1['dir'] = [0, -1]
                    elif event.key == pygame.K_s and player1['dir'][1] != -1: player1['dir'] = [0, 1]
                    elif event.key == pygame.K_a and player1['dir'][0] != 1: player1['dir'] = [-1, 0]
                    elif event.key == pygame.K_d and player1['dir'][0] != -1: player1['dir'] = [1, 0]
            
            if not game_over:
                # Move players
                move_player(player1['pos'], player1['dir'], player1['speed'])
                ai_move(difficulty)
                move_player(player2['pos'], player2['dir'], player2['speed'])
                
                # Check for power-up collision
                for powerup in powerups[:]:
                    if (abs(player1['pos'][0] - powerup['pos'][0]) < PLAYER_SIZE and 
                        abs(player1['pos'][1] - powerup['pos'][1]) < PLAYER_SIZE):
                        apply_powerup(player1, powerup)
                        powerups.remove(powerup)
                    elif (abs(player2['pos'][0] - powerup['pos'][0]) < PLAYER_SIZE and 
                          abs(player2['pos'][1] - powerup['pos'][1]) < PLAYER_SIZE):
                        apply_powerup(player2, powerup)
                        powerups.remove(powerup)
                
                # Add current positions to trails
                trails[0].append(player1['pos'][:])
                trails[1].append(player2['pos'][:])
                
                # Check for collisions
                if (check_collision(player1['pos'], trails[0]) or 
                    check_collision(player1['pos'], trails[1]) or 
                    player1['pos'][0] < 0 or player1['pos'][0] >= WIDTH or 
                    player1['pos'][1] < 0 or player1['pos'][1] >= HEIGHT):
                    if not player1['shield']:
                        game_over = True
                        score[1] += 1
                    else:
                        player1['shield'] = False
                if (check_collision(player2['pos'], trails[0]) or 
                    check_collision(player2['pos'], trails[1]) or 
                    player2['pos'][0] < 0 or player2['pos'][0] >= WIDTH or 
                    player2['pos'][1] < 0 or player2['pos'][1] >= HEIGHT):
                    if not player2['shield']:
                        game_over = True
                        score[0] += 1
                    else:
                        player2['shield'] = False
                
                # Update trails (simple length limit for performance)
                for trail in trails:
                    if len(trail) > WIDTH * HEIGHT // (PLAYER_SIZE ** 2):
                        trail.pop(0)
                
                # Spawn power-ups
                if len(powerups) < 3 and random.random() < 0.01:  # 1% chance per frame to spawn a power-up
                    spawn_powerup()
                
                # Decrease power-up duration
                for player in [player1, player2]:
                    if player['speed'] > 1:
                        player['speed'] = 1
                    if player['shield']:
                        player['shield'] = False  # Shield lasts only one collision

            draw_game()
            clock.tick(10 + difficulty * 2)  # Increase game speed with difficulty

        pygame.quit()

    # Run the main game
    main()

def game_4():

    # Global variables
    WIDTH, HEIGHT = 800, 600
    player_size = 20
    ghost_size = 20
    player_speed = 5
    ghost_speed = 3
    fast_ghost_speed = 6
    BLACK = (0, 0, 0)
    YELLOW = (255, 255, 0)
    RED = (255, 0, 0)
    WHITE = (255, 255, 255)
    special_dot_color = (255, 0, 0)  # Starts red
    special_dot_speed = 5  # How fast it changes color
    rainbow_dots_collected = 0

    def check_dot_collision(player_pos, dots, special_dot, score, special_dot_timer, rainbow_dots_collected, ghosts):
        global special_dot_color  # Now, this will modify the global variable

        for dot in dots[:]:
            if (player_pos[0] < dot[0] + 5 and player_pos[0] + player_size > dot[0] - 5 and
                player_pos[1] < dot[1] + 5 and player_pos[1] + player_size > dot[1] - 5):
                dots.remove(dot)
                ghosts_consumed = len(ghosts)
                score += ghosts_consumed
                for i in range(len(ghosts)):
                    ghosts[i] = [random.randint(0, WIDTH - ghost_size), random.randint(0, HEIGHT - ghost_size)]
    
            # Check for special dot collision
            if (player_pos[0] < special_dot[0] + 5 and player_pos[0] + player_size > special_dot[0] - 5 and
                player_pos[1] < special_dot[1] + 5 and player_pos[1] + player_size > special_dot[1] - 5):
                score += 10  # Add 10 points for eating the special dot
                special_dot = [random.randint(20, WIDTH - 20), random.randint(20, HEIGHT - 20)]  # Respawn special dot
                special_dot_color = (255, 0, 0)  # Reset color to start the cycle again
                special_dot_timer = 0
        
                # Increment rainbow dots collected
                rainbow_dots_collected += 1
                # Double the number of ghosts for each rainbow dot collected
                double_ghosts()

    def double_ghosts(ghosts, rainbow_dots_collected):
            # Calculate the multiplier based on rainbow dots collected
        multiplier = 2 ** rainbow_dots_collected
        # Ensure there's at least one ghost per original ghost
        new_ghosts_count = max(1, multiplier * 4)  # Starting with 4 ghosts
        # Generate new ghosts positions
        new_ghosts = [[random.randint(0, WIDTH - ghost_size), random.randint(0, HEIGHT - ghost_size)] for _ in range(new_ghosts_count)]
        ghosts = new_ghosts

    def check_game_over(score):
        if score <= 0:
            glitch_effect(win, "Not every gazelle crosses the river...")
            return False
        return True

    def update_score(score, win, font):
        text = font.render(f'Score: {score}', True, WHITE)
        win.blit(text, (10, 10))

    def draw(win, player_pos, ghosts, dots, special_dot, special_dot_color, score, font, maze):
        win.fill(BLACK)
        for y, row in enumerate(maze):
            for x, cell in enumerate(row):
                if cell == 1:  # Wall
                    pygame.draw.rect(win, (0, 0, 255), (x * 20, y * 20, 20, 20))
        # Draw player
        pygame.draw.rect(win, YELLOW, (player_pos[0], player_pos[1], player_size, player_size))
        # Draw ghosts
        for ghost in ghosts:
            pygame.draw.rect(win, RED, (ghost[0], ghost[1], ghost_size, ghost_size))
        # Draw dots
        for dot in dots:
            pygame.draw.circle(win, WHITE, (dot[0], dot[1]), 5)
        # Draw maze, player, ghosts, regular dots...
        pygame.draw.circle(win, special_dot_color, special_dot, 5)
        # Update score display
        update_score(score, win, font)
        pygame.display.update()

    def move_ghosts(ghosts, player_pos, player_moved, maze):
        for i in range(4):
            if player_moved:
                dx, dy = 0, 0  # Initialize movement deltas
            
                # Determine direction towards player or random for ghost 4
                if i < 2 or i == 2:
                    if ghosts[i][0] < player_pos[0]: dx = ghost_speed if i < 2 else fast_ghost_speed
                    elif ghosts[i][0] > player_pos[0]: dx = -ghost_speed if i < 2 else -fast_ghost_speed
                    if ghosts[i][1] < player_pos[1]: dy = ghost_speed if i < 2 else fast_ghost_speed
                    elif ghosts[i][1] > player_pos[1]: dy = -ghost_speed if i < 2 else -fast_ghost_speed
                else:  # Random movement for the fourth ghost
                    dx = random.choice([-ghost_speed, 0, ghost_speed])
                    dy = random.choice([-ghost_speed, 0, ghost_speed])
            
                # Check if the ghost can move in the chosen direction
                if can_move(ghosts[i][0] + dx, ghosts[i][1] + dy, maze):
                    ghosts[i][0] += dx
                    ghosts[i][1] += dy
                else:
                    # If the move is blocked, try moving only in one direction or not at all
                    if can_move(ghosts[i][0] + dx, ghosts[i][1], maze):
                        ghosts[i][0] += dx
                    elif can_move(ghosts[i][0], ghosts[i][1] + dy, maze):
                        ghosts[i][1] += dy
                    # If neither direction works, the ghost stays still or you could implement a pathfinding algorithm here

    def check_ghost_collision(player_pos, ghosts, score):
        for i, ghost in enumerate(ghosts):
            if (ghost[0] < player_pos[0] + player_size and 
                ghost[0] + ghost_size > player_pos[0] and 
                ghost[1] < player_pos[1] + player_size and 
                ghost[1] + ghost_size > player_pos[1]):
                score -= 1
                ghosts[i] = [random.randint(0, WIDTH - ghost_size), random.randint(0, HEIGHT - ghost_size)]

    def spawn_dots(dot_timer, dots):
        dot_timer += 1
        if dot_timer >= 90:  # 3 seconds at 30 FPS
            dots.append([random.randint(20, WIDTH - 20), random.randint(20, HEIGHT - 20)])
            dot_timer = 0

    def generate_maze(width, height):
        maze = [[1 for _ in range(width)] for _ in range(height)]

        def carve_path(x, y):
            maze[y][x] = 0  # 0 represents a path
            directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
            random.shuffle(directions)
            for dx, dy in directions:
                nx, ny = x + dx*2, y + dy*2
                if 0 <= ny < height and 0 <= nx < width and maze[ny][nx] == 1:
                    maze[y + dy][x + dx] = 0
                    carve_path(nx, ny)

        carve_path(1, 1)  # Start carving from near the top-left corner to leave a border
        return maze

    def remove_dead_ends(maze):
        def is_dead_end(x, y):
            if maze[y][x] == 0:  # If it's a path
                paths = sum(1 for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)] 
                            if 0 <= y + dy < len(maze) and 0 <= x + dx < len(maze[0]) and maze[y + dy][x + dx] == 0)
                return paths == 1  # Only one way in or out
            return False

        for y in range(1, len(maze) - 1):
            for x in range(1, len(maze[0]) - 1):
                if is_dead_end(x, y):
                    # Find a way to connect this dead end
                    directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
                    random.shuffle(directions)
                    for dx, dy in directions:
                        nx, ny = x + dx, y + dy
                        if maze[ny][nx] == 1:  # If it's a wall
                            maze[ny][nx] = 0  # Make it a path
                            break  # Only need to connect once

        return maze

    def can_move(x, y, maze):
        grid_x, grid_y = int(x // 20), int(y // 20)
        if 0 <= grid_x < len(maze[0]) and 0 <= grid_y < len(maze):
            return maze[grid_y][grid_x] == 0
        return False

    def glitch_effect(canvas, message):
        # Save the original surface
        original_surface = canvas.copy()

        # Define glitch parameters
        glitch_duration = 3000  # 1 second in milliseconds
        start_time = pygame.time.get_ticks()

        while pygame.time.get_ticks() - start_time < glitch_duration:
            # Clear the canvas
            canvas.fill(BLACK)
    
            # Pixelation effect
            for y in range(0, HEIGHT, 8):
                for x in range(0, WIDTH, 8):
                    # Choose a random 8x8 block from the original surface
                    block_x = random.randint(0, WIDTH - 8)
                    block_y = random.randint(0, HEIGHT - 8)
                    canvas.blit(original_surface, (x, y), (block_x, block_y, 8, 8))
    
            # Color shift effect
            for _ in range(100):  # Number of color shift blocks
                x = random.randint(0, WIDTH - 1)
                y = random.randint(0, HEIGHT - 1)
                w = random.randint(1, 10)
                h = random.randint(1, 10)
                color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                pygame.draw.rect(canvas, color, (x, y, w, h))
    
            # Screen tearing effect
            tear_y = random.randint(0, HEIGHT - 1)
            canvas.blit(original_surface, (0, tear_y), (0, 0, WIDTH, tear_y))
            canvas.blit(original_surface, (0, tear_y), (0, tear_y + 1, WIDTH, HEIGHT - tear_y))
    
            # Draw the message
            font = pygame.font.Font(None, 36)
            text_surface = font.render(message, True, (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
            canvas.blit(text_surface, (WIDTH // 2 - text_surface.get_width() // 2, HEIGHT // 2 - text_surface.get_height() // 2))
    
            # Update display
            pygame.display.flip()
    
            # Small delay to control frame rate
            pygame.time.delay(30)  # About 30 FPS

        # Restore the original surface
        canvas.blit(original_surface, (0, 0))
        pygame.display.flip()

    def game():
        global special_dot_color, rainbow_dots_collected  # Declare special_dot_color as global

        # Initialize pygame
        pygame.init()

        win = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Pac-Man AI")

        # Font for score display
        font = pygame.font.Font(None, 36)
        # Maze generation
        maze = generate_maze(WIDTH // 20, HEIGHT // 20)
        maze = remove_dead_ends(maze)
    
        # Game state
        player_pos = [WIDTH // 2, HEIGHT // 2]
        ghosts = [[random.randint(0, WIDTH - ghost_size), random.randint(0, HEIGHT - ghost_size)] for _ in range(4)]  # Start with 4 ghosts
        dots = []
        special_dot = [random.randint(20, WIDTH - 20), random.randint(20, HEIGHT - 20)]
        score = 20
        dot_timer = 0
        last_player_pos = player_pos.copy()
        player_moved = False
        rainbow_dots_collected = 0
        special_dot_color = (255, 0, 0)  # Starts red
        special_dot_speed = 5  # How fast it changes color
        rainbow_dots_collected = 0
        # Main game loop
        run = True
        clock = pygame.time.Clock()
        special_dot_timer = 0

        while run:
            clock.tick(30)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    run = False

            keys = pygame.key.get_pressed()
            if keys[pygame.K_a] and player_pos[0] > 0 and can_move(player_pos[0] - player_speed, player_pos[1], maze):
                player_pos[0] -= player_speed
                player_moved = True
            if keys[pygame.K_d] and player_pos[0] < WIDTH - player_size and can_move(player_pos[0] + player_speed, player_pos[1], maze):
                player_pos[0] += player_speed
                player_moved = True
            if keys[pygame.K_w] and player_pos[1] > 0 and can_move(player_pos[0], player_pos[1] - player_speed, maze):
                player_pos[1] -= player_speed
                player_moved = True
            if keys[pygame.K_s] and player_pos[1] < HEIGHT - player_size and can_move(player_pos[0], player_pos[1] + player_speed, maze):
                player_pos[1] += player_speed
                player_moved = True
            if keys[pygame.K_ESCAPE] or keys[pygame.K_q]:
                run = False
        
            # Update game state
            special_dot_timer += 1
            if special_dot_timer >= special_dot_speed:
                # Cycle through RGB colors for a rainbow effect
                if special_dot_color[0] > 0:  # Red to Green
                    special_dot_color = (special_dot_color[0] - 1, special_dot_color[1] + 1, 0)
                elif special_dot_color[1] > 0:  # Green to Blue
                    special_dot_color = (0, special_dot_color[1] - 1, special_dot_color[2] + 1)
                else:  # Blue to Red
                    special_dot_color = (special_dot_color[0] + 1, 0, special_dot_color[2] - 1)
                special_dot_timer = 0



            # Call functions with necessary parameters
            move_ghosts(ghosts, player_pos, player_moved, maze)
            spawn_dots(dot_timer, dots)
            check_ghost_collision(player_pos, ghosts, score)
            check_dot_collision(player_pos, dots, special_dot, score, special_dot_timer, rainbow_dots_collected, ghosts)
            run = check_game_over(score)
            draw(win, player_pos, ghosts, dots, special_dot, special_dot_color, score, font, maze)

            # Reset player moved flag
            player_moved = False

            # Game over check
            if not run:
                glitch_effect(win, "Game Over!")
                pygame.quit()
                sys.exit()


        pygame.quit()
    game()

def game_5():
    pass 

def check_and_reset_files(sec_url, base_url_file, sanitized_file_path, output_file_path):
    # Check if the base URL has changed
    reset_files = False
    if os.path.exists(base_url_file):
        with open(base_url_file, 'r') as file:
            last_base_url = file.read().strip()
            if last_base_url != sec_url:
                reset_files = True
    else:
        reset_files = True

    # Reset files if the base URL has changed
    if reset_files:
        print("Base URL has changed. Resetting tracking files.")
        with open(base_url_file, 'w') as file:
            file.write(sec_url)
        if os.path.exists(sanitized_file_path):
            os.remove(sanitized_file_path)
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

def download_files():
    # Path to the log file
    log_file_path = os.path.join(download_directory, 'download-legal-source-log.txt')

    # Read existing files from download_log.txt
    existing_files = set()
    if os.path.exists(log_file_path):
        with open(log_file_path, 'r') as log_file:
            existing_files = set(line.strip() for line in log_file.readlines())

    # Get the list of subdirectories
    subdirectory_names = [d for d in os.listdir(download_directory) if os.path.isdir(os.path.join(download_directory, d))]

    # Generate file URLs from subdirectory names
    file_urls = [f"{base_url}/{subdirectory_name}.zip" for subdirectory_name in subdirectory_names]
    expected_files = {url.split('/')[-1] for url in file_urls}
    
    # Determine missing files
    missing_files = expected_files - existing_files
    total_files = len(missing_files)
    skipped_files = len(existing_files) - (len(expected_files) - total_files)

    # Grab Edgar CIK master list.
    # Create a progress bar for the download process
    with tqdm(total=total_files, desc="Downloading files") as pbar:
        for url in file_urls:
            file_name = url.split('/')[-1]  # Extract file name from URL
            local_path = os.path.join(download_directory, file_name)

            if file_name in missing_files:
                attempt = 0
                while attempt < 4:
                    headers = {'User-Agent': "anonymous/FORTHELULZ@anonyops.com"}
                    try:
                        # Create request with headers
                        req = urllib.request.Request(url, headers=headers)
                        with urllib.request.urlopen(req) as response:
                            # Check for successful response
                            if response.getcode() != 200:
                                raise HTTPError(url, response.getcode(), "Non-200 status code", headers, None)
                            with open(local_path, 'wb') as f:
                                f.write(response.read())
                            print(f"\nDownloaded {file_name}")
                            break  # Exit retry loop if successful
                    except (HTTPError, URLError) as e:
                        print(f"Attempt {attempt + 1} failed to download {file_name}: {e}")

                        attempt += 1
                        if attempt == 3:  # Use backup headers on 4th attempt
                            print(f"Retrying with backup headers for {file_name}")
                            try:
                                backup_req = urllib.request.Request(url, headers=backup_headers)
                                with urllib.request.urlopen(backup_req) as response:
                                    if response.getcode() != 200:
                                        raise HTTPError(url, response.getcode(), "Non-200 status code", headers, None)
                                    with open(local_path, 'wb') as f:
                                        f.write(response.read())
                                    print(f"\nDownloaded {file_name}")
                                    break
                            except (HTTPError, URLError) as e:
                                print(f"Final attempt failed for {file_name}: {e}")

                pbar.update(1)  # Update progress bar for downloaded files
    
    # Append newly downloaded files to the log file
    with open(log_file_path, 'a') as log_file:
        for file_name in missing_files:
            log_file.write(file_name + '\n')

    print(f"\nSummary:")
    print(f"Files downloaded: {total_files}")
    print(f"Files skipped (already present): {skipped_files}")

# Function to download a single file with retry mechanism and logging
def download_file(url, directory, subdirectory_name, retries=10, delay=1):
    filename = os.path.join(directory, f"{subdirectory_name}.txt")

    # Check if the file already exists
    if os.path.exists(filename):
        print(f"File {filename} already exists. Skipping.")
        return True

    for attempt in range(retries):
        try:
            headers = {
                'User-Agent': "anonymous/FORTHELULZ@anonyops.com"
            }
            if verbose:
                print(f"Attempting to download {url}")

            # Create a request object with headers
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.getcode() != 200:
                    raise HTTPError(url, response.getcode(), "Non-200 status code", headers, None)
                
                if verbose:
                    print(f"Saving to {filename}...")
                with open(filename, 'wb') as file:
                    file.write(response.read())
                print(f"Downloaded: {filename}")
                md5_hash = hashlib.md5(content).hexdigest()
                # Log the source URL and timestamp
                timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                log_filename = os.path.join(directory, "download_log.txt")
                with open(log_filename, 'a') as log_file:
                    log_file.write(f"{subdirectory_name}.txt,{timestamp},{url},{md5_hash}\n")
                if verbose:
                    print(f"Logged download details to {log_filename}")

                # Verify file size
                file_size = os.path.getsize(filename)
                if verbose:
                    print(f"File size: {file_size} bytes")
                return True
        except (HTTPError, URLError, IOError) as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:  # No need to sleep after the last attempt
                time.sleep(delay * (2 ** attempt))  # Exponential backoff
    print(f"Failed to download {url} after {retries} retries")
    return False

def GUI_DL(url):
    base_download_dir = './edgar'
    error_log_path = 'error_log.txt'
    filename = os.path.basename(url)
    file_path = os.path.join(base_download_dir, filename)
    retries = 3
    delay = 1
    verbose = True

    for attempt in range(retries):
        try:
            headers = {
                'User-Agent': "anonymous/FORTHELULZ@anonyops.com"
            }
            if verbose:
                print(f"Attempting to download {url}")

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()  # Raises an exception for non-2xx status codes

            content = response.content

            if verbose:
                print(f"Saving to {file_path}...")
            with open(file_path, 'wb') as file:
                file.write(content)  # Write the content to the file
            print(f"Downloaded: {file_path}")

            # Log the source URL and timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            log_filename = os.path.join(base_download_dir, os.path.splitext(os.path.basename(url))[0] + '-legal-source-log.txt')
            
            # Ensure the directory exists for the log file
            os.makedirs(os.path.dirname(log_filename), exist_ok=True)
            
            # Calculate MD5 hash
            md5_hash = hashlib.md5(content).hexdigest()
            
            with open(log_filename, 'a') as log_file:
                log_file.write(f"{url},{file_path},{timestamp},{md5_hash}\n")
                log_file.write(f"URL: {url}\nDownloaded at: {timestamp}\n")
            if verbose:
                print(f"Logged download details to {log_filename}")
            
            # Verify file size
            file_size = os.path.getsize(file_path)
            if verbose:
                print(f"File size: {file_size} bytes")
            
            return file_path  # Return the path of the downloaded file

        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))  # Exponential backoff

    print(f"Failed to download {url} after {retries} retries")
    with open(error_log_path, 'a') as error_log_file:
        error_log_file.write(f"Failed to download {url} after {retries} retries\n")
    return None  # Return None if download fails after all retries

def testing(sec_url):
    base_url_file='base_url.txt'
    sanitized_file_path='sanitized_subdirectories.txt'
    output_file_path='completed_subdirectories.txt'
    download_directory='./edgar'
    error_log_path='error_log.txt'
    base_download_dir = './edgar'
    headers = {'User-Agent': "anonymous/FORTHELULZ@anonyops.com"}

    # Ensure the treasure vault exists
    os.makedirs(base_download_dir, exist_ok=True)

    print(f"Embarking on the quest for {sec_url}...")
    # The spell to conjure a file from the digital ether
    check_and_reset_files(sec_url, base_url_file, sanitized_file_path, output_file_path)

    folder_name = sec_url.rstrip('/').split('/')[-1]
    full_download_directory = os.path.join(base_download_dir, folder_name)
    print(f"Full download directory: {full_download_directory} - Here lies our treasure vault")

    # Here we call upon the ancient rites to reveal hidden paths
    subdirectories = scrape_subdirectories(sec_url)
    if not subdirectories:
        print(f"No hidden chambers found at {sec_url}. Exiting this quest.")
        return

    full_subdirectory_urls = [f"{sec_url.rstrip('/')}/{sub}" for sub in subdirectories]
    
    with open(sanitized_file_path, 'w') as sanitized_file:
        sanitized_file.write('\n'.join(full_subdirectory_urls))
    print(f"Sanitized list created: {sanitized_file_path} - The map to hidden chambers is drawn")

    if os.path.exists(output_file_path):
        with open(output_file_path, 'r') as file:
            completed_subdirectories = [line.strip() for line in file]
    else:
        completed_subdirectories = []

    os.makedirs(full_download_directory, exist_ok=True)
    print(f"Download directory created: {full_download_directory} - The vault is ready to receive its riches")

    total_subdirectories = len(full_subdirectory_urls)
    processed_subdirectories = len(completed_subdirectories)

    for subdirectory in full_subdirectory_urls:
        if subdirectory in completed_subdirectories:
            print(f"Skipping already plundered chamber: {subdirectory}")
            continue

        print(f"Venturing into the chamber: {subdirectory}")
        try:
            # Summoning the directory's content with an ancient spell
            soup = fetch_directory(subdirectory)
            txt_links = extract_txt_links(soup)
            # Extracting the scrolls of knowledge from the chamber
            print(f"Found txt links in {subdirectory}: {txt_links}")

            for txt_link in txt_links:
                txt_url = "https://www.sec.gov" + txt_link
                print(f"Downloading txt file: {txt_url} - Securing the scroll")
                if download_file(txt_url, full_download_directory,):  
                    with open(output_file_path, 'a') as completed_file:
                        completed_file.write(subdirectory + '\n')
                    break
                time.sleep(.1)  # A brief rest to avoid angering the digital spirits
        except Exception as e:
            print(f"Failed to access {subdirectory}: {e} - Beware, for this path is cursed!")
            with open('error_log.txt', 'a') as error_log_file:
                error_log_file.write(f"Failed to access {subdirectory}: {e}\n")

        processed_subdirectories += 1
        print(f"Progress: {processed_subdirectories}/{total_subdirectories} chambers explored.")

    remaining_subdirectories = [sub for sub in full_subdirectory_urls if sub not in completed_subdirectories]

    with open(sanitized_file_path, 'w') as sanitized_file:
        sanitized_file.write('\n'.join(remaining_subdirectories))

    print("Download complete for current CIK - The quest for this treasure trove ends.")

def run_main():
    # Define the base path relative to the home directory
    base_path = Path.cwd()
    # Normalize the path to the correct format for the current OS
    normalized_path = base_path.resolve()
    base_url_file='base_url.txt'

    # Convert the path to the appropriate format for Windows if needed
    if os.name == 'nt':  # Windows
        normalized_path = normalized_path.as_posix().replace('/', '\\')

    print("Normalized Path:", normalized_path)

    try:
        if not check_free_space(download_directory2):
            print("Not enough free space to proceed. Exiting.")
            sys.exit(1)
        while True:
            directory_part = input(
                "Please enter the CIK number of the Edgar directory to be scraped, or one of the following options:\n"
                "1. archives - search tool to find and list any companies SEC filings. Can also search for Last Names.\n"
                "2. csv - function to select and process a CSV created from searching the Edgar archives.\n"
                "3. view-files - To perform an Edgar inventory check.\n"
                "4. parse-files - To parse SEC filings after processing.\n"
                "5. help - To get information about all the things.\n"
                "69. AllYourBaseAreBelongToUs - An absolutely horrible option that fills up your ENTIRE harddrive with SEC filings.<< (hint: srsly NOT advised.)\n"
                "0. Return to main menu.\n"
                "Enter your choice: ").strip()

            if directory_part == "1" or directory_part == "archives":
                print("You have chosen to search the master archives and output a CSV of results for view-files and parse-files to use.")
                verify_and_prompt()
            elif directory_part == "2" or directory_part == "csv":
                csv_files = list_csv_files("./edgar")
                if not csv_files:
                    print("No CSV files found.")
                    continue

                print("Available CSV files (without '_results.csv'):")
                for i, file in enumerate(csv_files):
                    print(f"{i + 1}: {file[:-len('_results.csv')]}")

                file_choice = int(input("Select a CSV file by number or enter 0 to exit: "))
                if file_choice == 0:
                    continue

                if 1 <= file_choice <= len(csv_files):
                    csv_file = csv_files[file_choice - 1]
                    print(f"Selected CSV file: {csv_file}")
                    CSV_EXTRACTION_METHOD = input("use archves URL listings or crawl SEC site? (options are 'url' or 'crawl')").strip()
                    if CSV_EXTRACTION_METHOD == 'url':
                        # function to read URLs from CSV and download them directly from created list.
                        download_from_csv(csv_file)
                    elif CSV_EXTRACTION_METHOD == 'crawl':
                        # function to use the CIK's to crawl and download in a more aggressive way.
                        download_from_crawling(csv_file)
                    elif directory_part == "0":
                        continue
                    else:
                        print("please enter url, crawl, or 0 to go back to main menu")
                    print("Processing of CSV URLs complete.")
                else:
                    print("Invalid choice.")
            elif directory_part == "3" or directory_part == "view-files":
                print("Beginning downloaded Edgar filings check.")
                clean()
            elif directory_part == "4" or directory_part == "parse-files":
                print("Proceeding with parse option.")
                parse(sec_urls=None)
            elif directory_part == "5" or directory_part == "help":
                print_help()
            elif directory_part == "69" or directory_part == "AllYourBaseAreBelongToUs":
                print("Easter egg found. This allows you to download ALL SEC filings.")
                sec_processing_pipeline()
            elif directory_part == "0":
                continue
            elif len(directory_part) > 5 and directory_part.isdigit():
                sec_url = edgar_url + directory_part
                testing(sec_url)
            else:
                print("Invalid input. Please try again.")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        print("Script execution finished.")

def search_master_archives(search_term, directory):
    global tqdm
    search_term = search_term.strip()
    if not search_term or ' ' in search_term:
        print("Invalid search term provided. Please enter a single term.")
        return
    output_dir='./'

    # Ensure the output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    results_file = os.path.join(output_dir, f"{search_term}_results.csv")
    zip_files = [os.path.join(root, file) for root, _, files in os.walk(directory) for file in files if file.endswith(".zip")]

    with open(results_file, 'w', newline='') as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["CIK", "Company Name", "Form Type", "Date Filed", "Filename"])

        # Wrap the iterable with tqdm for a progress bar
        for zip_path in tqdm(zip_files, desc="Searching", unit="file"):
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_file:
                    for zip_info in zip_file.infolist():
                        if zip_info.filename.endswith(".idx"):
                            with zip_file.open(zip_info) as idx_file:
                                raw_data = idx_file.read()
                                encoding = chardet.detect(raw_data)['encoding']
                                lines = raw_data.decode(encoding, errors='replace').splitlines()
                                for line in lines:
                                    parts = line.split('|')
                                    if len(parts) < 5:
                                        continue
                                    company_name = parts[1].strip()
                                    if search_term.lower() in company_name.lower():
                                        csv_writer.writerow(parts)
            except Exception as e:
                print(f"Error processing file {zip_path}: {e}")

    if os.path.exists(results_file) and os.path.getsize(results_file) > 0:
        print(f"Search results saved to {results_file}")
    else:
        print(f"No results found for '{search_term}'")
        if os.path.exists(results_file):
            os.remove(results_file)

def verify_and_prompt():
    def search_and_prompt():
        if not failed_downloads:
            print("All files downloaded successfully.")
            while True:
                search_term = get_valid_search_term()  # Use the existing function to validate the search term
                if search_term:
                    search_master_archives(search_term, download_directory)
                    another_search = input("Would you like to search for another term? (yes/no): ").strip().lower()
                    if another_search not in ["yes", "y"]:
                        print("Game On Anon")
                        break
                else:
                    print("Search term cannot be empty..")
        else:
            print("Some files failed to download. Please check the error list.")

    # Run the search and prompt logic in a separate thread
    search_thread = threading.Thread(target=search_and_prompt)
    search_thread.start()
    search_thread.join()  # Wait for the thread to complete

def get_valid_search_term():
    forbidden_terms = {'a', 'b', 'c', 'edgar', 'www', 'https', '*', '**'}
    special_terms = {'gamestop', 'cohen', 'chewy'}
    deep_value_terms = {'citi', 'citigroup', 'salomon', 'lehman', 'stearns', 'barney', 
                        'smith', 'stanley', 'traveler', 'wamu', 'jpm', 'buffet', 
                        'goldman', 'ubs', 'suisse', 'nomura'}
    while True:
        search_term = input("Enter search term: ").strip().lower()
        if len(search_term) == 1 or search_term.isdigit():
            return None
        if not search_term:
            print("why did you enter a blank query? c'mon.")
            continue

        if (len(search_term) == 1 and search_term.isalnum()) or search_term in forbidden_terms:
            print("anon, don't fucking search for that. c'mon.")
            
            if search_term in forbidden_terms:
                confirmation = input("THIS IS NOT A GOOD IDEA. YOU SURE? (y/n): ").strip().lower()
                if confirmation == 'y':
                    return search_term
                else:
                    continue

        if search_term in deep_value_terms:
            print("DOING SOME DEEP FUCKING VALUE DILIGENCE? CAN DO ANON.")
            return search_term

        if search_term in special_terms:
            if search_term == 'gamestop' or search_term == 'cohen':
                print("POWER TO THE PLAYERS!")
            elif search_term == 'chewy':
                print("CHEWY. INVESTMENT ADVICE THAT STICKS")
            return search_term

        if search_term == 'gill':
            print("ONE GILL IS NOT LIKE THE OTHERS. ONE IS NOT A CAT.")
            return search_term

        return search_term

def download_from_csv(csv_file):
    base_url = "https://www.sec.gov/Archives/"
    base_download_dir = './edgar'
    headers = {'User-Agent': "anonymous/FORTHELULZ@anonyops.com"}
    retries=3
    delay=1
    verbose=True
    # Count total rows to set progress bar length
    with open(csv_file, newline='', encoding='utf-8') as csvfile:
        total_rows = sum(1 for row in csv.reader(csvfile)) - 1  # Subtract 1 for header
    
    # Reset file pointer to start
    with open(csv_file, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader, None)  # Skip header but save it
        rows = list(reader)  # Read all rows into memory for easy manipulation
        
        # Ensure 'Download Location' is in the header
        if 'Download Location' not in header:
            header.append('Download Location')
        
        # Initialize progress bar
        pbar = tqdm(total=total_rows, desc="Downloading", unit="file")
        
        failed_downloads = []
        for row in rows:
            if len(row) < 5:
                pbar.update(1)
                continue
            
            cik = row[0]
            url = base_url + row[4]
            filename = url.split('/')[-1]
            cik_dir = os.path.join(base_download_dir, cik)
            os.makedirs(cik_dir, exist_ok=True)
            full_path = os.path.join(cik_dir, filename)
            
            download_success = False
            for attempt in range(retries):
                try:
                    # Corrected here: Use of Request and urlopen
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as response:
                        if response.getcode() != 200:
                            raise HTTPError(url, response.getcode(), "Non-200 status code", headers, None)
                        with open(full_path, 'wb') as file:
                            file.write(response.read())  
                        download_success = True
                        break
                except (HTTPError, URLError, IOError) as e:
                    print(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < retries - 1:  # No need to sleep after the last attempt
                        time.sleep(delay * (2 ** attempt))  # Exponential backoff
            
            if download_success:
                download_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                row.append(full_path)  # Add the download location to the row
            else:
                failed_downloads.append(url)
                row.append('Failed')  # Indicate failure in the download location
            
            pbar.update(1)
        
        pbar.close()
    
    # Write back to CSV with the new column
    with open(csv_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)  # Write the updated header
        writer.writerows(rows)  # Write the updated rows

    # Create HTML index with the name based on the CSV file
    base_name = os.path.splitext(os.path.basename(csv_file))[0]
    html_file_name = f"{base_name}_index.html"

    with open(html_file_name, 'w', encoding='utf-8') as htmlfile:
        htmlfile.write('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Download Index</title>
            <style>
                table {
                    border-collapse: collapse;
                    width: 100%;
                }
                th, td {
                    border: 1px solid black;
                    padding: 8px;
                    text-align: left;
                }
                th {
                    cursor: pointer;
                    background-color: #f2f2f2;
                }
                .ascii-art {
                    font-family: monospace;
                    white-space: pre;
                }
            </style>
            <script>
                function sortTable(n) {
                    var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
                    table = document.getElementById("downloadIndex");
                    switching = true;
                    dir = "asc";
                    while (switching) {
                        switching = false;
                        rows = table.rows;
                        for (i = 1; i < (rows.length - 1); i++) {
                            shouldSwitch = false;
                            x = rows[i].getElementsByTagName("TD")[n];
                            y = rows[i + 1].getElementsByTagName("TD")[n];
                            if (dir == "asc") {
                                if (x.innerHTML.toLowerCase() > y.innerHTML.toLowerCase()) {
                                    shouldSwitch = true;
                                    break;
                                }
                            } else if (dir == "desc") {
                                if (x.innerHTML.toLowerCase() < y.innerHTML.toLowerCase()) {
                                    shouldSwitch = true;
                                    break;
                                }
                            }
                        }
                        if (shouldSwitch) {
                            rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                            switching = true;
                            switchcount++;
                        } else {
                            if (switchcount == 0 && dir == "asc") {
                                dir = "desc";
                                switching = true;
                            }
                        }
                    }
                }
            </script>
        </head>
        <body>
            <div class="ascii-art">
                <!-- Place for ASCII art -->
                frames = []
            </div>
            <table id="downloadIndex">
                <tr>
                    ''' + ''.join(f'<th onclick="sortTable({i})">{h}</th>' for i, h in enumerate(header)) + '''
                </tr>
        ''')
        for row in rows:
            htmlfile.write('<tr>')
            for item in row:
                if item.startswith('./edgar') or item == 'Failed':
                    htmlfile.write(f'<td><a href="file://{os.path.abspath(item)}">{item}</a></td>' if item != 'Failed' else f'<td>{item}</td>')
                else:
                    htmlfile.write(f'<td>{item}</td>')
            htmlfile.write('</tr>')
        htmlfile.write('''
            </table>
        </body>
        </html>
        ''')

    print(f"HTML index with sorting capability created: {html_file_name}")

    # Remember to add a timestamp to each row during the download process, like:
    # row.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

def download_from_crawling(csv_file):
    from concurrent.futures import ThreadPoolExecutor

    """
    Initiates a grand adventure in data acquisition from the depths of the SEC's EDGAR system,
    using a CSV file as the treasure map. Each CIK is a new quest, each file a piece of lore to be gathered.
    
    :param csv_file: The ancient scroll (CSV file) containing CIKs, the keys to untold digital riches.
    """
    base_download_dir = './edgar'
    ciks = set()  # A set, because who likes duplicates in their treasure chest?

    # Reading the ancient scroll
    with open(csv_file, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        # Skipping the sacred header, if it exists
        next(reader, None) 
        for row in reader:
            if len(row) < 1:
                print(f"Skipping {row} due to lack of substance: likely a cursed line in the scroll.")
                continue
            cik = row[0]
            ciks.add(cik)

    # Ensure the treasure vault exists
    os.makedirs(base_download_dir, exist_ok=True)
    header = ['CIK', 'URL', 'Download Location', 'Status']
    rows = []

    # Here, we call upon the `download_file` spell, our brave knight in this saga
    def download_file(url, directory, retries=3, delay=1):
        # The spell to conjure a file from the digital ether
        for attempt in range(retries):
            try:
                headers = {
                    'User-Agent': "anonymous/FORTHELULZ@anonyops.com"
                }                    
                print(f"Attempting to download {url}...")
                # The spell to conjure a file from the digital ether
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.getcode() != 200:
                        raise HTTPError(url, response.getcode(), "Non-200 status code", headers, None)
                
                    filename = os.path.join(directory, os.path.basename(url))
                    with open(filename, 'wb') as file:
                        file.write(response.read())  # Changed from response.content to response.read()
                    print(f"Downloaded: {filename}")
                    md5_hash = hashlib.md5(content).hexdigest()
                    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                    log_filename = os.path.join(directory, os.path.splitext(os.path.basename(url))[0] + '-legal-source-log.txt')
                    with open(log_filename, 'w') as log_file:
                        log_file.write(f"URL: {url}\nDownloaded at: {timestamp},\n{filename} with MD5 :{md5_hash}\n")
                    print(f"Logged download details to {log_filename}")
                    file_size = os.path.getsize(filename)
                    print(f"File size: {file_size} bytes - the weight of this digital artifact")
                    return True

            except (HTTPError, URLError) as e:
                print(f"Attempt {attempt + 1} failed for {url}: {e} - A dragon guards this treasure!")
                if attempt < retries - 1:  # No need to sleep after the last attempt
                    time.sleep(delay * (attempt + 1))
        print(f"Failed to download {url} after {retries} retries - The treasure remains elusive")
        return False

    #for cik in ciks:
    def process_cik(cik):
        # The URL where our quest begins
        sec_url_full = f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        print(f"Embarking on the quest for {sec_url_full}...")

        folder_name = sec_url_full.rstrip('/').split('/')[-1]
        full_download_directory = os.path.join(base_download_dir, folder_name)
        print(f"Full download directory: {full_download_directory} - Here lies our treasure vault")

        # Here we call upon the ancient rites to reveal hidden paths
        subdirectories = scrape_subdirectories(sec_url_full)
        if not subdirectories:
            print(f"No hidden chambers found at {sec_url_full}. Exiting this quest.")
            #continue

        full_subdirectory_urls = [f"{sec_url_full.rstrip('/')}/{sub}" for sub in subdirectories]
        
        sanitized_file_path = 'sanitized_subdirectories.txt'
        with open(sanitized_file_path, 'w') as sanitized_file:
            sanitized_file.write('\n'.join(full_subdirectory_urls))
        print(f"Sanitized list created: {sanitized_file_path} - The map to hidden chambers is drawn")

        output_file_path = 'completed_subdirectories.txt'
        if os.path.exists(output_file_path):
            with open(output_file_path, 'r') as file:
                completed_subdirectories = [line.strip() for line in file]
        else:
            completed_subdirectories = []

        os.makedirs(full_download_directory, exist_ok=True)
        print(f"Download directory created: {full_download_directory} - The vault is ready to receive its riches")

        total_subdirectories = len(full_subdirectory_urls)
        processed_subdirectories = len(completed_subdirectories)

        for subdirectory in full_subdirectory_urls:
            if subdirectory in completed_subdirectories:
                print(f"Skipping already plundered chamber: {subdirectory}")
                continue

            print(f"Venturing into the chamber: {subdirectory}")
            try:
                # Summoning the directory's content with an ancient spell
                soup = fetch_directory(subdirectory)
                # Extracting the scrolls of knowledge from the chamber
                txt_links = extract_txt_links(soup)
                print(f"Found txt links in {subdirectory}: {txt_links} - Scrolls of lore discovered")
                for txt_link in txt_links:
                    txt_url = "https://www.sec.gov" + txt_link
                    print(f"Downloading txt file: {txt_url} - Securing the scroll")
                    download_success = download_file(txt_url, full_download_directory)
                    download_location = os.path.join(full_download_directory, os.path.basename(txt_url)) if download_success else 'Failed'
                    rows.append([cik, txt_url, download_location, 'Success' if download_success else 'Failed'])
                    if download_success:
                        with open(output_file_path, 'a') as completed_file:
                            completed_file.write(subdirectory + '\n')
                        break
                    time.sleep(.1)  # A brief rest to avoid angering the digital spirits
            except Exception as e:
                print(f"Failed to access {subdirectory}: {e} - Beware, for this path is cursed!")
                with open('error_log.txt', 'a') as error_log_file:
                    error_log_file.write(f"Failed to access {subdirectory}: {e}\n")

            processed_subdirectories += 1
            print(f"Progress: {processed_subdirectories}/{total_subdirectories} chambers explored.")

        remaining_subdirectories = [sub for sub in full_subdirectory_urls if sub not in completed_subdirectories]

        with open(sanitized_file_path, 'w') as sanitized_file:
            sanitized_file.write('\n'.join(remaining_subdirectories))

        print("Download complete for current CIK - The quest for this treasure trove ends.")
    # Using ThreadPoolExecutor for concurrent processing of CIKs
    with ThreadPoolExecutor(max_workers=4) as executor:  # Adjust max_workers as needed
        executor.map(process_cik, ciks)

    # After all downloads, write to CSV
    with open(csv_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)
        writer.writerows(rows)

    # Create HTML index
    html_file_name = os.path.splitext(csv_file)[0] + '_index.html'
    with open(html_file_name, 'w', encoding='utf-8') as htmlfile:
        htmlfile.write('<!DOCTYPE html><html><head><title>Download Index</title></head><body><table border="1">')
        htmlfile.write('<tr>' + ''.join(f'<th>{h}</th>' for h in header) + '</tr>')
        for row in rows:
            htmlfile.write('<tr>')
            for item in row:
                if item.startswith('./edgar') or item == 'Failed':
                    htmlfile.write(f'<td><a href="file://{os.path.abspath(item)}">{item}</a></td>' if item != 'Failed' else f'<td>{item}</td>')
                else:
                    htmlfile.write(f'<td><a href="{item}">{item}</a></td>')
            htmlfile.write('</tr>')
        htmlfile.write('</table></body></html>')

    print(f"Quest completed for {len(ciks)} CIKs. CSV updated and HTML index created. May their data enrich our realms!")

    while True:
        repeat_variable = input("Would you like to embark on another quest for a CIK's worth of files? (yes/no): ").strip().lower()
        if repeat_variable == "yes":
            new_cik = input("Enter the new CIK: ").strip()
            new_sec_url = f"https://www.sec.gov/Archives/edgar/data/{new_cik}"
            print(f"Preparing for a new quest with CIK: {new_cik}")
            # Here you might want to call `process_cik(new_cik)` directly or handle it in another way
        elif repeat_variable == "no":
            print("Thank you for your bravery in this quest. Farewell, noble seeker of knowledge!")
            break
        else:
            print("Please choose 'yes' to continue your quest or 'no' to rest.")

def edgar_CIKs():
    # Configuration
    url = 'https://sec.gov/Archives/edgar/cik-lookup-data.txt'
    filename = './edgar_CIKs.csv'
    directory = '.'  # Directory where the log file will be saved
    retries=3
    delay=1 
    verbose=True
    # Function to download the file
    def download_file(url, filename, retries, delay, verbose):
        # Check if the file already exists
        if os.path.exists(filename):
            print(f"File {filename} already exists. Skipping.")
            return True

        for attempt in range(retries):
            try:
                headers = {'User-Agent': "anonymous/FORTHELULZ@anonyops.com"}

                if verbose:
                    print(f"Attempting to download {url}")
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.getcode() != 200:
                        raise HTTPError(url, response.getcode(), "Non-200 status code", headers, None)

                if verbose:
                    print(f"Saving to {filename}...")
                with open(filename, 'wb') as file:
                    file.write(response.read())
                print(f"Downloaded: {filename}")
                md5_hash = hashlib.md5(content).hexdigest()
                # Log the source URL and timestamp
                timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                log_filename = os.path.join(directory, os.path.splitext(os.path.basename(url))[0] + '-legal-source-log.txt')
                with open(log_filename, 'w') as log_file:
                    log_file.write(f"URL: {url}\n")
                    log_file.write(f"Downloaded at: {timestamp}\n")
                    log_file.write(f"MD5: {md5_hash}\n")
                print(f"Logged download details to {log_filename}")

                # Verify file size
                file_size = os.path.getsize(filename)
                if verbose:
                    print(f"File size: {file_size} bytes")
                return True
            except (HTTPError, URLError) as e:
                print(f"Attempt {attempt + 1} failed for {url}: {e} - A dragon guards this treasure!")
                if attempt < retries - 1:  # No need to sleep after the last attempt
                    time.sleep(delay * (attempt + 1))
        print(f"Failed to download {url} after {retries} retries")
        return False

    # Call the download function
    return download_file(url, filename, retries, delay, verbose)

def fetch_directory(url):
    retries=3
    delay=1
    verbose=True
    headers = {
        'User-Agent': "anonymous/FORTHELULZ@anonyops.com"  # Assuming you've defined this header elsewhere
    }
    
    for attempt in range(retries):
        try:
            print(f"Fetching URL: {url}")
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.getcode() != 200:
                    raise HTTPError(url, response.getcode(), "Non-200 status code", headers, None)
                time.sleep(delay)  # Slow down to avoid rate limiting
                # Here we read the content and then parse it with BeautifulSoup
                content = response.read()
                return BeautifulSoup(content, 'html.parser')
        except (HTTPError, URLError) as e:
            print(f"Attempt {attempt + 1} failed for {url}: {e}")
            if attempt < retries - 1:  # No sleep til brooklyn
                time.sleep(delay * (attempt + 1))  # Exponential backoff
    raise Exception(f"Failed to fetch {url} after {retries} retries")

def scrape_subdirectories(sec_url):
    soup = fetch_directory(sec_url)
    rows = soup.find_all('a')
    subdirectories = []
    for row in rows:
        href = row.get('href')
        # Check if the href is a subdirectory link with 18-digit numeric names
        if href and href.startswith('/Archives/edgar/data/') and len(href.strip('/').split('/')[-1]) == 18:
            subdirectories.append(href.strip('/').split('/')[-1])
        else:
            print(f"Skipping non-matching href: {href}")  # Log non-matching hrefs for debugging
    print(f"Scraped subdirectories: {subdirectories}\n ")
    return subdirectories

def extract_txt_links(soup):
    links = soup.find_all('a')
    txt_links = [link.get('href') for link in links if link.get('href') and link.get('href').endswith('.txt')]
    return txt_links

def list_csv_files(directory):
    return [f for f in os.listdir(directory) if f.endswith('_results.csv')]

def read_sec_urls_from_csv(csv_file):
    valid_cik_numbers = []
    
    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        for row in reader:
            if row:
                item = row[0].strip()
                # Check if the item is a valid CIK (an 8 to 10 digit number)
                if item.isdigit() and 6 <= len(item):
                    valid_cik_numbers.append(item)
    
    return valid_cik_numbers

def process_cik(cik, **kwargs):
    # Construct the correct URL for the CIK subdirectory
    sec_url_full = f"https://www.sec.gov/Archives/edgar/data/{cik}/"
    print(f"Processing {sec_url_full}...")

    # Call the main function with the corrected URL and paths
    testing(sec_url=sec_url_full)

def load_replacements_from_csv(csv_file):
    replacements = {}
    try:
        with open(csv_file, 'r') as file:
            reader = csv.reader(file)
            for row in reader:
                if len(row) >= 2:
                    folder_name = row[0].strip()
                    replacement_word = row[1].strip()
                    replacements[folder_name] = replacement_word
    except Exception as e:
        print(f"Error reading CSV file {csv_file}: {e}")
    return replacements

def apply_replacements(directory, replacements):
    parts = directory.split(os.sep)
    for i, part in enumerate(parts):
        parts[i] = replacements.get(part, part)
    return os.sep.join(parts)

def list_directories(base_path, replacements_csv):
    replacements = load_replacements_from_csv(replacements_csv)
    directories = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
    if not directories:
        print("No directories found in the specified path.")
        sys.exit(1)
    print("Available directories:")
    for index, directory in enumerate(directories):
        # Replace directory names if they exist in the replacements dictionary
        display_name = replacements.get(directory, directory)
        # Count files, excluding log files
        file_count = len([f for f in os.listdir(os.path.join(base_path, directory)) if f.endswith('.txt')])
        print(f"{index + 1}. {display_name} ({file_count // 2} files)")
    return directories

def get_user_choice(num_options):
    while True:
        try:
            choice = int(input(f"Enter the number of your choice (1-{num_options}): "))
            if 1 <= choice <= num_options:
                return choice - 1
            else:
                print("Invalid choice. Please choose a number within the range.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def clean():
    import sys

    def load_cik_replacements(cik_file):
        backup_file="edgar_CIK2.csv"
        cik_replacements = {}
    
        # First, try to load from the primary file
        with open(cik_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            # Skip the header row if it exists
            next(reader, None)
            for row in reader:
                if len(row) >= 3:
                    # Assuming CIK is in the third column (index 2) and company name in the second (index 1)
                    cik_key = row[2].strip()
                    company_name = row[1].strip()
                    cik_replacements[cik_key] = company_name

        return cik_replacements

    def extract_filing_form_type(file_path):
        if file_path.lower().endswith('.html'):
            return extract_filing_type_from_html(file_path)
        else:
            return extract_filing_type_from_text(file_path)

    def extract_filing_type_from_text(file_path):
        # First, try to detect the encoding
        with open(file_path, 'rb') as file:
            raw_data = file.read(1000)  # Read the first 1000 bytes for encoding detection
            result = chardet.detect(raw_data)
            detected_encoding = result['encoding']

        try:
            # Try to open with the detected encoding
            with open(file_path, 'r', encoding=detected_encoding, errors='replace') as file:
                header_lines = file.readlines()[:20]  # Read the first 20 lines for header info
        except UnicodeDecodeError:
            # If the detected encoding fails, fall back to a common encoding
            with open(file_path, 'r', encoding='latin-1', errors='replace') as file:
                header_lines = file.readlines()[:20]

        for line in header_lines:
            match = re.search(r'CONFORMED SUBMISSION TYPE:\s*(.*)', line)
            if match:
                return match.group(1).strip()
    
        return 'Unknown'

    def extract_filing_type_from_html(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file, 'html.parser')
        
        # Search for meta tags that might include filing type
        meta_tag = soup.find('meta', {'name': re.compile('SEC FORM TYPE', re.IGNORECASE)})
        if meta_tag and 'content' in meta_tag.attrs:
            return meta_tag['content'].strip()

        # Check for common HTML structures for filing types
        header_div = soup.find('div', {'id': 'header'})
        if header_div:
            text = header_div.get_text()
            match = re.search(r'CONFORMED SUBMISSION TYPE:\s*(.*)', text)
            if match:
                return match.group(1).strip()
        
        return 'Unknown'

    def categorize_unknown_form_type(form_type):
        known_patterns = {
            '10-K': 'Annual Report',
            '10-Q': 'Quarterly Report',
            '10-Q/A': 'Amendment to Quarterly Report',
            '10-K/A': 'Amendment to Annual Report',
            '8-K': 'Current Report',
            '8-K/A': 'Amendment to Current Report',
            'DEF 14A': 'Proxy Statement',
            'DEF 14A/A': 'Amendment to Proxy Statement',
            'F-1': 'Registration Statement',
            'F-1/A': 'Amendment to Registration Statement',
            'Form 3': 'Initial Statement of Beneficial Ownership',
            'Form 3/A': 'Amendment to Initial Statement of Beneficial Ownership',
            'Form 4': 'Statement of Changes in Beneficial Ownership',
            'Form 4/A': 'Amendment to Statement of Changes in Beneficial Ownership',
            'Form 5': 'Annual Statement of Changes in Beneficial Ownership',
            'Form 5/A': 'Amendment to Annual Statement of Changes in Beneficial Ownership',
            'Form ADV': 'Investment Adviser Registration',
            'Form ADV/A': 'Amendment to Investment Adviser Registration',
            'Form D': 'Notice of Exempt Offering of Securities',
            'Form D/A': 'Amendment to Notice of Exempt Offering of Securities',
            'Form N-1A': 'Registration Statement for Open-End Management Investment Companies',
            'Form N-1A/A': 'Amendment to Registration Statement for Open-End Management Investment Companies',
            'Form N-CSR': 'Certified Shareholder Report',
            'Form N-CSR/A': 'Amendment to Certified Shareholder Report',
            'Form N-Q': 'Quarterly Schedule of Portfolio Holdings',
            'Form N-Q/A': 'Amendment to Quarterly Schedule of Portfolio Holdings',
            '13D': 'Beneficial Ownership Report',
            '13D/A': 'Amendment to Beneficial Ownership Report',
            '13G': 'Beneficial Ownership Report',
            '13G/A': 'Amendment to Beneficial Ownership Report',
            '13F': 'Institutional Investment Manager Report',
            '13F/A': 'Amendment to Institutional Investment Manager Report',
            'S-1': 'Registration Statement',
            'S-1/A': 'Amendment to Registration Statement',
            'S-3': 'Registration Statement',
            'S-3/A': 'Amendment to Registration Statement',
            'S-4': 'Registration Statement',
            'S-4/A': 'Amendment to Registration Statement',
            'S-8': 'Registration Statement',
            'S-8/A': 'Amendment to Registration Statement',
            'S-11': 'Registration Statement',
            'S-11/A': 'Amendment to Registration Statement',
            'S-12': 'Registration Statement',
            'S-12/A': 'Amendment to Registration Statement',
            'S-15': 'Registration Statement',
            'S-15/A': 'Amendment to Registration Statement',
            'N-2': 'Registration Statement',
            'N-2/A': 'Amendment to Registration Statement',
            'N-3': 'Registration Statement',
            'N-3/A': 'Amendment to Registration Statement',
            'N-4': 'Registration Statement',
            'N-4/A': 'Amendment to Registration Statement',
            'N-5': 'Registration Statement',
            'N-5/A': 'Amendment to Registration Statement',
            'N-6': 'Registration Statement',
            'N-6/A': 'Amendment to Registration Statement',
            'N-8A': 'Notification of Registration',
            'N-8A/A': 'Amendment to Notification of Registration',
            'N-8B-2': 'Statement of Registration',
            'N-8B-2/A': 'Amendment to Statement of Registration'
        }
        return known_patterns.get(form_type, 'Download Logs')

    def count_filing_form_types(directory):
        form_type_counts = {}
        file_paths = []

        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path):
                form_type = extract_filing_form_type(file_path)
                if form_type == 'Unknown':
                    # Attempt to categorize unknown types
                    form_type = categorize_unknown_form_type(form_type)
                if form_type in form_type_counts:
                    form_type_counts[form_type] += 1
                else:
                    form_type_counts[form_type] = 1
                file_paths.append((file_path, form_type))
        
        return form_type_counts, file_paths

    def display_subfolders(base_directory, cik_replacements):
        subdirs = [d for d in os.listdir(base_directory) if os.path.isdir(os.path.join(base_directory, d))]
    
        # Create a list of tuples (original_name, converted_name) and sort by converted_name
        subdir_list = [(subdir, cik_replacements.get(subdir, subdir)) for subdir in subdirs]
        sorted_subdirs = sorted(subdir_list, key=lambda x: x[1].lower())
    
        # Create a dictionary to store the sorted subdirectories
        converted_subdirs = {}
        for i, (subdir, converted_name) in enumerate(sorted_subdirs, start=1):
            converted_subdirs[i] = (subdir, converted_name)
        
            counts, _ = count_filing_form_types(os.path.join(base_directory, subdir))
            total_files = sum(counts.values())
            if total_files <= 5:
                form_list = ', '.join(f"{form_type} ({count} files)" for form_type, count in counts.items())
                print(f"{i}. {converted_name} - {total_files} ({form_list})")
            else:
                print(f"{i}. {converted_name} - {total_files} files")
    
        return converted_subdirs

    def display_files_and_counts(subdir_path):
        counts, file_paths = count_filing_form_types(subdir_path)
        
        # Sort the counts dictionary alphabetically by form type
        sorted_counts = dict(sorted(counts.items()))
        
        for i, (form_type, count) in enumerate(sorted_counts.items()):
            print(f"{i + 1}. {form_type} ({count} files)")
        
        return sorted_counts, file_paths

    def clean_file(file_path):
        temp_file_path = file_path + '.tmp'

        try:
            # Copy the original file to a temp file
            shutil.copy(file_path, temp_file_path)

            # Read content and process it
            with open(temp_file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            # Remove blank lines
            content = '\n'.join(line.strip() for line in content.splitlines() if line.strip())

            # Find the position of the first occurrence of the GRAPHIC pattern
            graphic_pattern = re.compile(r'\bGRAPHIC\b\s*\d+\s*\S+\.(jpg|gif|png)\s*\bGRAPHIC\b', re.IGNORECASE | re.DOTALL)
            match = graphic_pattern.search(content)
            if match:
                # Remove everything from the start of the GRAPHIC pattern to the end of the file
                content = content[:match.start()]
            
            # Write cleaned content back to temp file
            with open(temp_file_path, 'w', encoding='utf-8') as file:
                file.write(content)

            return temp_file_path
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
            return None

    def clear_console():
        # Check for the operating system
        if os.name == 'nt':  # Windows
            os.system('cls')
        else:  # Unix/Linux/Mac
            os.system('clear')

    def view_file_content(file_path):
        temp_file_path = clean_file(file_path)
        if temp_file_path:
            try:
                # Clear the console before showing file content
                clear_console()
                
                with open(temp_file_path, 'r', encoding='utf-8') as file:
                    print("\nFile Content:")
                    print(file.read())
            finally:
                # Remove the temporary file after viewing
                os.remove(temp_file_path)

    def process_file(file_path):
        try:
            def extract_submission_type(file_path):
                """Extract the CONFORMED SUBMISSION TYPE from the file header."""
                with open(file_path, 'r', encoding='utf-8') as file:
                    header_lines = file.readlines()[:20]  # Read the first 20 lines for header info
                for line in header_lines:
                    match = re.search(r'CONFORMED SUBMISSION TYPE:\s*(.*)', line)
                    if match:
                        submission_type = match.group(1).strip()
                        # Adjust the submission type string if it ends with "/A"
                        if submission_type.endswith("/A"):
                            return submission_type.replace("/A", "A")
                        return submission_type
                return 'Unknown'
                #return os.path.basename(file_path).split('.')[0]  #Extract submission type from file name or content.

            def process_10k_reports(file_path):
                """Process files of type 10-K, 10-K/A."""
                submission_type = extract_submission_type(file_path)
                if submission_type in ['10-K', '10-K/A']:
                    print(f"Processing 10-K Report file: {file_path}")

                    # Initialize an empty list to collect rows for CSV output
                    csv_rows = []

                    try:
                        tree = ET.parse(file_path)
                        root = tree.getroot()

                        # Extract general information about the company
                        companyName = root.findtext('.//CompanyName', default='').strip()
                        fiscalYearEnd = root.findtext('.//FiscalYearEnd', default='').strip()
                        totalAssets = root.findtext('.//TotalAssets', default='').strip()
                        totalLiabilities = root.findtext('.//TotalLiabilities', default='').strip()
                        shareholdersEquity = root.findtext('.//ShareholdersEquity', default='').strip()
                        revenue = root.findtext('.//Revenue', default='').strip()
                        netIncome = root.findtext('.//NetIncome', default='').strip()
                        operatingCashFlow = root.findtext('.//OperatingCashFlow', default='').strip()
                        investingCashFlow = root.findtext('.//InvestingCashFlow', default='').strip()
                        financingCashFlow = root.findtext('.//FinancingCashFlow', default='').strip()
                        earningsPerShare = root.findtext('.//EarningsPerShare', default='').strip()

                        # Extract management's discussion and analysis
                        mdnaResultsOfOperations = root.findtext('.//MDNAResultsOfOperations', default='').strip()
                        mdnaLiquidityAndCapitalResources = root.findtext('.//MDNALiquidityAndCapitalResources', default='').strip()

                        # Extract executive compensation information
                        executiveCompensation = root.findtext('.//ExecutiveCompensation', default='').strip()

                        # Extract legal proceedings
                        legalProceedings = root.findtext('.//LegalProceedings', default='').strip()

                        # Extract key risks
                        keyRisks = root.findtext('.//KeyRisks', default='').strip()

                        # Only include rows where all required values are non-empty
                        if (companyName and fiscalYearEnd and totalAssets and totalLiabilities and shareholdersEquity and
                            revenue and netIncome and operatingCashFlow and investingCashFlow and financingCashFlow and
                            earningsPerShare):
                            csv_rows.append([
                                file_path,
                                'URL_not_found',  # Placeholder for source URL
                                companyName,
                                fiscalYearEnd,
                                totalAssets,
                                totalLiabilities,
                                shareholdersEquity,
                                revenue,
                                netIncome,
                                operatingCashFlow,
                                investingCashFlow,
                                financingCashFlow,
                                earningsPerShare,
                                mdnaResultsOfOperations,
                                mdnaLiquidityAndCapitalResources,
                                executiveCompensation,
                                legalProceedings,
                                keyRisks
                            ])
                    except ET.ParseError as e:
                        print(f"Error parsing XML file {file_path}: {e}")
                        return []
                else:
                    print(f"Unknown submission type for file: {file_path}")
                    return []

                return csv_rows

            def process_current_reports(file_path):
                """Process files of type 8-K, 8-K/A."""
                submission_type = extract_submission_type(file_path)
                if submission_type in ['8-K', '8-K/A']:
                    print(f"Processing Current Report file: {file_path}")

                    # Initialize an empty list to collect rows for CSV output
                    csv_rows = []

                    try:
                        tree = ET.parse(file_path)
                        root = tree.getroot()

                        # Extract information based on XML structure
                        for transaction in root.findall('.//Transaction'):  # Adjust the XPath as needed
                            securityTitle = transaction.findtext('securityTitle', default='').strip()
                            transactionDate = transaction.findtext('transactionDate', default='').strip()
                            transactionFormType = transaction.findtext('transactionFormType', default='').strip()
                            transactionCode = transaction.findtext('transactionCode', default='').strip()
                            transactionShares = transaction.findtext('transactionShares', default='').strip()
                            transactionPricePerShare = transaction.findtext('transactionPricePerShare', default='').strip()
                            transactionAcquiredDisposedCode = transaction.findtext('transactionAcquiredDisposedCode', default='').strip()
                            underlyingSecurityTitle = transaction.findtext('underlyingSecurityTitle', default='').strip()
                            underlyingSecurityShares = transaction.findtext('underlyingSecurityShares', default='').strip()
                            sharesOwnedFollowingTransaction = transaction.findtext('sharesOwnedFollowingTransaction', default='').strip()
                            directOrIndirectOwnership = transaction.findtext('directOrIndirectOwnership', default='').strip()

                            # Only include rows where all required values are non-zero
                            if (securityTitle and transactionDate and transactionFormType and transactionCode and
                                transactionShares and transactionPricePerShare and transactionAcquiredDisposedCode and
                                underlyingSecurityTitle and underlyingSecurityShares and sharesOwnedFollowingTransaction and
                                directOrIndirectOwnership):
                                csv_rows.append([
                                    file_path,
                                    'URL_not_found',  # Placeholder for source URL
                                    securityTitle,
                                    transactionDate,
                                    transactionFormType,
                                    transactionCode,
                                    transactionShares,
                                    transactionPricePerShare,
                                    transactionAcquiredDisposedCode,
                                    underlyingSecurityTitle,
                                    underlyingSecurityShares,
                                    sharesOwnedFollowingTransaction,
                                    directOrIndirectOwnership
                                ])

                    except ET.ParseError as e:
                        print(f"Error parsing XML file {file_path}: {e}")

                    return csv_rows
                else:
                    print(f"Unknown submission type for file: {file_path}")
                    return []

            def process_proxy_statements(file_path):
                """Process files of type DEF 14A, DEF 14A/A."""
                submission_type = extract_submission_type(file_path)
                if submission_type in ['DEF 14A', 'DEF 14A/A']:
                    print(f"Processing Proxy Statement file: {file_path}")

                    # Initialize an empty list to collect rows for CSV output
                    csv_rows = []

                    try:
                        tree = ET.parse(file_path)
                        root = tree.getroot()

                        # Extract executive compensation information
                        execCompensation = root.findtext('.//ExecutiveCompensation', default='').strip()
                        
                        # Extract director information
                        directorsInfo = root.findtext('.//DirectorsInformation', default='').strip()
                        
                        # Extract shareholder proposals
                        shareholderProposals = root.findtext('.//ShareholderProposals', default='').strip()
                        
                        # Extract corporate governance information
                        corpGovernance = root.findtext('.//CorporateGovernance', default='').strip()

                        # Only include rows where all required values are non-empty
                        if (execCompensation and directorsInfo and shareholderProposals and corpGovernance):
                            csv_rows.append([
                                file_path,
                                'URL_not_found',  # Placeholder for source URL
                                execCompensation,
                                directorsInfo,
                                shareholderProposals,
                                corpGovernance
                            ])

                    except ET.ParseError as e:
                        print(f"Error parsing XML file {file_path}: {e}")

                    return csv_rows
                else:
                    print(f"Unknown submission type for file: {file_path}")
                    return []

            def process_registration_statements(file_path):
                """Process files of type F-1, F-1/A, S-1, S-1/A, S-3, S-3/A, S-4, S-4/A."""
                submission_type = extract_submission_type(file_path)
                if submission_type in ['F-1', 'F-1/A', 'S-1', 'S-1/A', 'S-3', 'S-3/A', 'S-4', 'S-4/A']:
                    print(f"Processing Registration Statement file: {file_path}")

                    # Initialize an empty list to collect rows for CSV output
                    csv_rows = []

                    try:
                        tree = ET.parse(file_path)
                        root = tree.getroot()

                        # Extract general information about the registration
                        issuerName = root.findtext('.//IssuerName', default='').strip()
                        offeringAmount = root.findtext('.//OfferingAmount', default='').strip()
                        sharesOffered = root.findtext('.//SharesOffered', default='').strip()
                        underwriterName = root.findtext('.//UnderwriterName', default='').strip()
                        useOfProceeds = root.findtext('.//UseOfProceeds', default='').strip()

                        # Only include rows where all required values are non-empty
                        if (issuerName and offeringAmount and sharesOffered and underwriterName and useOfProceeds):
                            csv_rows.append([
                                file_path,
                                'URL_not_found',  # Placeholder for source URL
                                issuerName,
                                offeringAmount,
                                sharesOffered,
                                underwriterName,
                                useOfProceeds
                            ])

                    except ET.ParseError as e:
                        print(f"Error parsing XML file {file_path}: {e}")

                    return csv_rows
                else:
                    print(f"Unknown submission type for file: {file_path}")
                    return []

            def process_insider_trading_reports(file_path):
                """Process files of type Form 3, Form 3/A, Form 4, Form 4/A, Form 5, Form 5/A."""
                submission_type = extract_submission_type(file_path)
                if submission_type in ['Form 3', 'Form 3/A', 'Form 4', 'Form 4/A', 'Form 5', 'Form 5/A']:
                    print(f"Processing Insider Trading Report file: {file_path}")

                    # Initialize an empty list to collect rows for CSV output
                    csv_rows = []

                    try:
                        tree = ET.parse(file_path)
                        root = tree.getroot()

                        # Extract insider trading information
                        insiderName = root.findtext('.//InsiderName', default='').strip()
                        reportDate = root.findtext('.//ReportDate', default='').strip()
                        transactionDate = root.findtext('.//TransactionDate', default='').strip()
                        transactionType = root.findtext('.//TransactionType', default='').strip()
                        sharesAcquired = root.findtext('.//SharesAcquired', default='').strip()
                        sharesDisposed = root.findtext('.//SharesDisposed', default='').strip()
                        sharesOwnedFollowingTransaction = root.findtext('.//SharesOwnedFollowingTransaction', default='').strip()

                        # Only include rows where all required values are non-empty
                        if (insiderName and reportDate and transactionDate and transactionType and sharesAcquired and
                            sharesDisposed and sharesOwnedFollowingTransaction):
                            csv_rows.append([
                                file_path,
                                'URL_not_found',  # Placeholder for source URL
                                insiderName,
                                reportDate,
                                transactionDate,
                                transactionType,
                                sharesAcquired,
                                sharesDisposed,
                                sharesOwnedFollowingTransaction
                            ])

                    except ET.ParseError as e:
                        print(f"Error parsing XML file {file_path}: {e}")

                    return csv_rows
                else:
                    print(f"Unknown submission type for file: {file_path}")
                    return []

            def process_investment_company_forms(file_path):
                """Process files of type Form ADV, Form ADV/A, Form D, Form D/A, Form N-1A, Form N-1A/A, Form N-CSR, Form N-CSR/A, Form N-Q, Form N-Q/A."""
                submission_type = extract_submission_type(file_path)
                if submission_type in ['Form ADV', 'Form ADV/A', 'Form D', 'Form D/A', 'Form N-1A', 'Form N-1A/A', 'Form N-CSR', 'Form N-CSR/A', 'Form N-Q', 'Form N-Q/A']:
                    print(f"Processing Investment Company Form file: {file_path}")

                    # Initialize an empty list to collect rows for CSV output
                    csv_rows = []

                    try:
                        tree = ET.parse(file_path)
                        root = tree.getroot()

                        # Extract investment company information
                        investmentCompanyName = root.findtext('.//InvestmentCompanyName', default='').strip()
                        totalAssets = root.findtext('.//TotalAssets', default='').strip()
                        totalLiabilities = root.findtext('.//TotalLiabilities', default='').strip()
                        netAssets = root.findtext('.//NetAssets', default='').strip()
                        netIncome = root.findtext('.//NetIncome', default='').strip()
                        dividends = root.findtext('.//Dividends', default='').strip()
                        capitalStock = root.findtext('.//CapitalStock', default='').strip()
                        sharesOutstanding = root.findtext('.//SharesOutstanding', default='').strip()

                        # Only include rows where all required values are non-empty
                        if (investmentCompanyName and totalAssets and totalLiabilities and netAssets and netIncome and
                            dividends and capitalStock and sharesOutstanding):
                            csv_rows.append([
                                file_path,
                                'URL_not_found',  # Placeholder for source URL
                                investmentCompanyName,
                                totalAssets,
                                totalLiabilities,
                                netAssets,
                                netIncome,
                                dividends,
                                capitalStock,
                                sharesOutstanding
                            ])

                    except ET.ParseError as e:
                        print(f"Error parsing XML file {file_path}: {e}")

                    return csv_rows
                else:
                    print(f"Unknown submission type for file: {file_path}")
                    return []

            def process_beneficial_ownership_reports(file_path):
                """Process files of type 13D, 13D/A, 13G, 13G/A, 13F, 13F/A."""
                submission_type = extract_submission_type(file_path)
                if submission_type in ['13D', '13D/A', '13G', '13G/A', '13F', '13F/A']:
                    print(f"Processing Beneficial Ownership Report file: {file_path}")

                    # Initialize an empty list to collect rows for CSV output
                    csv_rows = []

                    try:
                        tree = ET.parse(file_path)
                        root = tree.getroot()

                        # Extract beneficial ownership information
                        reportingPersonName = root.findtext('.//ReportingPersonName', default='').strip()
                        reportingPersonAddress = root.findtext('.//ReportingPersonAddress', default='').strip()
                        securityTitle = root.findtext('.//SecurityTitle', default='').strip()
                        sharesOwned = root.findtext('.//SharesOwned', default='').strip()
                        percentageOwned = root.findtext('.//PercentageOwned', default='').strip()
                        reportingPersonType = root.findtext('.//ReportingPersonType', default='').strip()

                        # Only include rows where all required values are non-empty
                        if (reportingPersonName and reportingPersonAddress and securityTitle and sharesOwned and
                            percentageOwned and reportingPersonType):
                            csv_rows.append([
                                file_path,
                                'URL_not_found',  # Placeholder for source URL
                                reportingPersonName,
                                reportingPersonAddress,
                                securityTitle,
                                sharesOwned,
                                percentageOwned,
                                reportingPersonType
                            ])

                    except ET.ParseError as e:
                        print(f"Error parsing XML file {file_path}: {e}")

                    return csv_rows
                else:
                    print(f"Unknown submission type for file: {file_path}")
                    return []
                    # Map of processing functions
                           
            # Define a dictionary to map form types to processing functions
            processing_functions = {
                ('10-K', '10-KA'): process_10k_reports,
                ('8-K', '8-KA'): process_current_reports,
                ('DEF 14A', 'DEF 14AA'): process_proxy_statements,
                ('F-1', 'F-1A', 'S-1', 'S-1A', 'S-3', 'S-3A', 'S-4', 'S-4A'): process_registration_statements,
                ('Form 3', 'Form 3A', 'Form 4', 'Form 4A', 'Form 5', 'Form 5A'): process_insider_trading_reports,
                ('Form ADV', 'Form ADVA', 'Form D', 'Form DA', 'Form N-1A', 'Form N-1AA', 'Form N-CSR', 'Form N-CSRA', 'Form N-Q', 'Form N-QA'): process_investment_company_forms,
                ('13D', '13DA', '13G', '13GA', '13F', '13FA'): process_beneficial_ownership_reports,
            }
        
            form_type = extract_submission_type(file_path)
            processing_function = next((func for keys, func in processing_functions.items() if form_type in keys), lambda fp: [])
    
            return processing_function(file_path)
        except Exception as e:
            print(f"Error exporting files: {e}")

    def export_files(selected_files, save_location):
        try:
            print(f"Files to process: {len(selected_files)}")
        
            # Define txt_file_path before the loop
            txt_file_path = os.path.splitext(save_location)[0] + '.txt'
        
            with open(save_location, 'w', newline='', encoding='utf-8') as csvfile:
                csvwriter = csv.writer(csvfile)
        
                # Write headers
                headers = ['File', 'Source URL', 'Content']
                csvwriter.writerow(headers)
    
                for file_path in selected_files:
                    # Normalize the file path to use the correct separator
                    file_path = os.path.normpath(file_path)
        
                    if not file_path.endswith('.txt'):
                        print(f"Skipping non-txt file: {file_path}")
                        continue
        
                    if not os.path.exists(file_path):
                        print(f"File does not exist: {file_path}")
                        continue
                    elif not os.access(file_path, os.R_OK):
                        print(f"File is not readable: {file_path}")
                        continue
                
                    print(f"Processing file: {file_path}")

                    try:
                        with open(file_path, 'r', encoding='utf-8') as file:
                            content = file.read()  # Read the entire file content
            
                        # Extract content between <TEXT> and </TEXT>
                        text_content_match = re.search(r'<TEXT>(.*?)</TEXT>', content, re.DOTALL)
                        if text_content_match:
                            text_content = text_content_match.group(1)
                        else:
                            print(f"No text content found in {file_path}") 
                            continue

                        # Clean HTML tags and unescape HTML entities
                        cleaned_content = re.sub('<[^<]+?>', '', html.unescape(text_content)).strip()

                        source_log_file = os.path.splitext(file_path)[0] + '-legal-source-log.txt'
                        if os.path.exists(source_log_file):
                            with open(source_log_file, 'r', encoding='utf-8') as log_file:
                                source_url = log_file.readline().strip()
                        else:
                            source_url = 'URL not found'

                        print(f"Source log file not found for {file_path}")
                        # After processing the file, before saving
                        print(f"File processed: {file_path}")
                        print(f"Default save location: {save_location}")

                        # CSV export
                        csvwriter.writerow([file_path, source_url, cleaned_content[:500]])  # Limit to first 500 characters for CSV

                        # Create a corresponding .txt file for plain text export
                        txt_file_path = os.path.splitext(save_location)[0] + '.txt'
                        with open(txt_file_path, 'a', encoding='utf-8') as txtfile:
                            # Write the file path as the first line
                            txtfile.write(f"File: {file_path}\n")
        
                            # Split the cleaned content into lines and filter out empty lines
                            non_empty_lines = [line for line in cleaned_content.split('\n') if line.strip()]
                            if non_empty_lines:
                                # Write non-empty lines
                                txtfile.write('\n'.join(non_empty_lines) + '\n')

                        print(f"Processing file: {file_path}")

                    except Exception as e:
                        print(f"Error processing file: {e}")
                        return []
                    except Exception as e:
                            print(f"Error processing {file_path}: {e}")
    
            print(f"Exported data to {save_location}")
            print(f"Exported plain text to {txt_file_path}")
        except Exception as e:
            print(f"Error exporting files: {e}")

    base_directory = './edgar'  # Base directory path
    cik_file = './edgar_CIKs.csv'  # CSV file with CIK replacements
    cik_replacements = load_cik_replacements(cik_file)
    
    while True:
        # Display subfolders for selection
        converted_subdirs = display_subfolders(base_directory, cik_replacements)

        while True:
            try:
                # Prompt user to select a subfolder
                subfolder_choice = int(input("\nSelect a subfolder by number (or 0 to exit): "))
                if subfolder_choice == 0:
                    break
            
                # Get selected subfolder details
                selected_subdir, converted_name = converted_subdirs.get(subfolder_choice, (None, None))
                if not selected_subdir:
                    print("Invalid choice. Please select a valid number.")
                    continue
            
                subdir_path = os.path.join(base_directory, selected_subdir)
                print(f"\nSelected subfolder: {converted_name}")
                break  # Exit the input loop if a valid choice is made

                while True:
                    # Display file counts and paths for the selected subfolder
                    counts, file_paths = display_files_and_counts(subdir_path)

                    try:
                        # Prompt user to select a filing form type
                        form_choice = int(input("\nSelect a filing form type by number (or 0 to go back): "))
                        if form_choice == 0:
                            break

                        selected_form = list(counts.keys())[form_choice - 1]
                        selected_files = [f for f, t in file_paths if t == selected_form]

                        if not selected_files:
                            print("No files found for this form type.")
                            continue

                        # Ask if user wants to export all files of the selected type
                        export_choice = input(f"\nDo you want to export all files of type '{selected_form}' to CSV? (y/n): ").strip().lower()
                
                        if export_choice == 'y':
                            # Prompt user to amend save location
                            user_input = input("Do you wish to change the save location? (y/n): ")
                            if user_input.lower() == 'y':
                                new_save_location = input("Enter new save location (full path): ")
                                if os.path.isdir(os.path.dirname(new_save_location)) or os.path.dirname(new_save_location) == '':
                                    save_location = new_save_location
                                    print(f"Save location updated to: {save_location}")
                                    export_files(selected_files, save_location)
                                else:
                                    print("Invalid directory. Using default location.")
                            else:
                                print("Using default save location.")
                                # Define export location using CIK and file type
                                save_location = f"edgar/{selected_subdir}-{selected_form}.csv"
                                # Call export_files function
                                export_files(selected_files, save_location)

                        elif export_choice == 'n':
                            while True:
                                print(f"\nFiles for form type '{selected_form}':")
                                for i, file_path in enumerate(selected_files):
                                    print(f"{i+1}. {os.path.basename(file_path)}")

                                try:
                                    # Prompt user to select a file
                                    file_choice = int(input("\nSelect a file by number (or 0 to go back): "))
                                    if file_choice == 0:
                                        break
                                    selected_file = selected_files[file_choice - 1]
                                    view_file_content(selected_file)
                                except (ValueError, IndexError):
                                    print("Invalid choice. Please select a valid file number.")
                        else:
                            print("Invalid choice. Please select 'y' to export or 'n' to proceed with file selection.")
                
                    except (ValueError, IndexError):
                        print("Invalid choice. Please select a valid form type number.")
            except ValueError:
                print("Invalid input. Please enter a number.")

def parse(sec_urls=None):  

    # Global variables
    files_found_count = 0
    verbose = False
    done = False
    
    def load_cik_replacements(cik_file):
        """Load CIK replacements from the provided CSV file, using the second column for company names and the third for CIK keys."""
        cik_replacements = {}
        with open(cik_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            # Skip the header row if it exists
            next(reader, None)
            for row in reader:
                if len(row) >= 3:
                    # company_name is from the second column (index 1)
                    company_name = row[1].strip()
                    # cik_key is from the third column (index 2)
                    cik_key = row[2].strip()
                    cik_replacements[cik_key] = company_name
        return cik_replacements

    def display_subfolders(base_directory, cik_replacements):
        """Display subfolders in the base directory with converted names."""
        subdirs = [d for d in os.listdir(base_directory) if os.path.isdir(os.path.join(base_directory, d))]
    
        converted_subdirs = {}
        for i, subdir in enumerate(sorted(subdirs), 1):
            subdir_path = os.path.join(base_directory, subdir)
            converted_name = cik_replacements.get(subdir, subdir)
            converted_subdirs[i] = (subdir, converted_name)
        
            # Count files in the subdirectory
            total_files = sum(1 for file in os.listdir(subdir_path) if os.path.isfile(os.path.join(subdir_path, file)))
        
            # Display the directory name with file count
            print(f"{i}. {converted_name} - {total_files} files")
    
        return converted_subdirs    

    def custom_animation(verbose=False):
        if verbose:
            return # skip the animation if verbose is enabled
    
        marquee_text = " ...following the rabbit... "
        marquee_length = 50
        marquee_position = -26
        while not done:
            if marquee_position < 0:
                display_text = " " * abs(marquee_position) + marquee_text[:marquee_length + marquee_position]
            else:
                display_text = marquee_text[marquee_position:marquee_position + marquee_length].ljust(marquee_length)
            #os.system('cls' if os.name == 'nt' else 'clear')
            sys.stdout.write(f"Files found: {files_found_count}\n")
            sys.stdout.write(display_text + '\n' + frames[marquee_position % len(frames)])
            sys.stdout.flush()
            time.sleep(0.1)
            marquee_position = (marquee_position + 1) % len(marquee_text)
        sys.stdout.write('\r')
    
    def handle_error(error_message):
        global done
        done = True
        #if not verbose:
        #    animation_thread.join()
        print(f"Error: {error_message}")
        print("lost the rabbits tail")
        sys.exit(1)
    
    def verbose_print(message):
        if verbose:
            print(message)

    def search_files(directory, pattern):
        global files_found_count
        for root, dirs, files in os.walk(directory):
            for file in files:
                if re.search(pattern, file):
                    files_found_count += 1
                    verbose_print(f"Found file: {os.path.join(root, file)}")
                    process_file(os.path.join(root, file))

    def process_file(file_path):
        class MLStripper(HTMLParser):
            def __init__(self):
                super().__init__()
                self.reset()
                self.strict = False
                self.convert_charrefs = True
                self.text = []

            def handle_data(self, d):
                self.text.append(d)

            def get_data(self):
                return ''.join(self.text)

        def strip_tags(html):
            s = MLStripper()
            s.feed(html)
            return s.get_data()

        # Normalize the path first to handle any mixed separators
        file_path = os.path.normpath(file_path)
    
        # Then, ensure the path uses the correct separators for the current OS
        if os.name == 'nt':  # Windows
            file_path = file_path.replace('/', '\\')
        else:  # Linux/Mac
            file_path = file_path.replace('\\', '/')

        try:
            verbose_print(f"Processing file: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()  # Read the entire file content

            # Extract content between <TEXT> tags
            matches = re.findall(r'<TEXT>(.*?)</TEXT>', content, re.DOTALL)
            if not matches:
                verbose_print("No <TEXT> tags found.")
                return

            # Process and clean each match line by line
            cleaned_lines = []
            for match in matches:
                lines = match.split('\n')  # Split into lines
                for line in lines:
                    clean_line = strip_tags(line).strip()  # Clean HTML tags
                    if clean_line:  # Only add if there's content after cleaning
                        cleaned_lines.append(clean_line)

            if not cleaned_lines:
                verbose_print("No clean text extracted after processing.")
                return

            # Save cleaned content to text file preserving line structure
            txt_save_location = save_location.replace('.csv', '.txt')
            with open(txt_save_location, 'a', encoding='utf-8') as txtfile:
                txtfile.write(f"File: {file_path}\n")
                for line in cleaned_lines:
                    txtfile.write(f"{line}\n")
                txtfile.write('\n' + '-' * 50 + '\n\n')  # Add a line of dashes for separation

            # Save cleaned content to CSV file
            with open(save_location, 'a', newline='', encoding='utf-8') as csvfile:
                csvwriter = csv.writer(csvfile)
                # Get the source URL from the corresponding "-legal-source-log.txt" file
                source_log_file = file_path.replace('.txt', '-legal-source-log.txt')
                source_url = 'URL not found'
                if os.path.exists(source_log_file):
                    with open(source_log_file, 'r', encoding='utf-8') as log_file:
                        source_url = log_file.readline().strip()

                # Here, we join lines back into blocks for CSV since CSV doesn't handle multi-line entries well
                text_blocks = [' '.join(cleaned_lines[i:i+50]) for i in range(0, len(cleaned_lines), 50)]  # Grouping lines into blocks
                for block in text_blocks:
                    csvwriter.writerow([file_path, source_url, block])

        except Exception as e:
            handle_error(f"Error processing file {file_path}: {e}")

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Process some files.')
    parser.add_argument('-v', '--verbose', action='store_true', help='enable verbose mode')
    args = parser.parse_args()
    verbose = args.verbose
    
    base_directory = './edgar'  # Base directory path
    cik_file = 'edgar_CIK2.csv'  # CSV file with CIK replacements
    
    # Load CIK replacements
    cik_replacements = load_cik_replacements(cik_file)

    # Display subfolders for selection
    converted_subdirs = display_subfolders(base_directory, cik_replacements)

    while True:
        # Prompt user to select a subfolder
        subfolder_choice = int(input("\nSelect a subfolder by number (or 0 to exit): "))
        if subfolder_choice == 0:
            print("Exiting subfolder selection.")
            break
            
        # Get selected subfolder details
        selected_subdir, converted_name = converted_subdirs.get(subfolder_choice, (None, None))
        if selected_subdir is None:
            print("Invalid choice. Please select a valid number.")
            continue
            
        subdir_path = os.path.join(base_directory, selected_subdir)
        print(f"\nSelected subfolder: {converted_name}")
        print(f"Path: {subdir_path}")

        # Input for search operations
        search_term = input("Enter the search term. single word only. (default is 'basket'): ") or 'basket'
        search_directory = subdir_path
        save_location = f"../{converted_name}-{search_term}.csv"
        
        # Verify the directory exists
        if not os.path.exists(search_directory):
            print(f"Warning: '{search_directory}' does not exist. Defaulting to '{subdir_path}'.")
            search_directory = subdir_path

        try:
            # Use glob to find all files recursively
            files = glob.glob(os.path.join(search_directory, '**', '*'), recursive=True)
    
            # Filter files based on the search term
            files_found_count = 0
            files_to_process = []
            for file in files:
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        if search_term in f.read():
                            files_to_process.append(file)
                            files_found_count += 1
                except UnicodeDecodeError:
                    # Skip files that can't be read as text (e.g., binary files)
                    continue
    
            verbose_print(f"Files found: {files_found_count}")

            # Process each file and write to output files
            for file in files_to_process:
                process_file(file)

            # Stop the custom animation if not verbose
            #if not verbose:
            #    done = True
            #    animation_thread.join()

            print(f"Output written to {save_location}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        break

def codex():
    """Introductory function to clear the screen, display ASCII art, and prompt the user."""
    # ANSI escape codes for colors
    COLORS = [
        '\033[31m',  # Red
        '\033[33m',  # Yellow
        '\033[32m',  # Green
        '\033[36m',  # Cyan
        '\033[34m',  # Blue
        '\033[35m',  # Magenta
    ]

    RESET = '\033[0m'  # Reset to default color

    def colorize_text(text):
        """Colorize the text with a rainbow gradient."""
        color_cycle = itertools.cycle(COLORS)
        colored_text = ''
        for char in text:
            if char == '\n':
                colored_text += char
            else:
                colored_text += next(color_cycle) + char
        return colored_text + RESET

    def get_terminal_width():
        """Get the current width of the terminal window."""
        try:
            # Get terminal size (columns, lines)
            columns, _ = os.get_terminal_size()
        except AttributeError:
            # Default width if os.get_terminal_size() is not available (e.g., on Windows)
            columns = 80
        return columns

    def display_text_normally(text, width=80):
        """Display the given text with word wrap and ensure newlines are preserved."""
        # Split the text into lines and handle each line individually
        lines = text.split('\n')
        wrapped_lines = []
        
        for line in lines:
            # Wrap each line of text
            wrapped_lines.append(textwrap.fill(line, width=width))
        
        # Join the wrapped lines back together with newlines in between
        wrapped_text = '\n'.join(wrapped_lines)
        print(wrapped_text)

    def display_hardcoded_ascii_art():
        """Display hardcoded ASCII art with rainbow gradient."""
        ascii_art = """\
mmmmmmm m    m mmmmmm          mmm   mmmm  mmmm   mmmmmm m    m
   #    #    # #             m"   " m"  "m #   "m #       #  # a
   #    #mmmm# #mmmmm        #      #    # #    # #mmmmm   ##  
   #    #    # #             #      #    # #    # #       m""m 
   #    #    # #mmmmm         "mmm"  #mm#  #mmm"  #mmmmm m"  "m
"""
        print(colorize_text(ascii_art))
        time.sleep(3)  # Show for 3 seconds

    def prompt_user():
        """Prompt the user to choose between learning SEC forms, Market Instruments, or quitting."""
        while True:
            print("\nPlease choose an option:")
            print("1. Learn about SEC forms pt. 1")
            print("2. Learn about SEC forms pt. 1")
            print("3. Learn about Market Instruments")
            print("Q. Quit")

            choice = input("Enter 1, 2, or Q: ").strip().lower()
            
            if choice == '1' or choice == 'sec forms':
                text_content ="""
1. 10-K
   - Description: The 10-K is an annual report filed by publicly traded companies to provide a comprehensive overview of the company's financial performance. It includes audited financial statements, management discussion and analysis, and details on operations, risk factors, and governance.
   - Investopedia Link: https://www.investopedia.com/terms/1/10-k.asp

2. 10-K/A
   - Description: The 10-K/A is an amendment to the annual 10-K report. It is used to correct or update information that was originally filed in the 10-K.
   - Investopedia Link: https://www.investopedia.com/terms/1/10-k.asp

3. 10-Q
   - Description: The 10-Q is a quarterly report that companies must file after the end of each of the first three quarters of their fiscal year. It provides an update on the company's financial performance, including unaudited financial statements and management discussion.
   - Investopedia Link: https://www.investopedia.com/terms/1/10-q.asp

4. 10-Q/A
   - Description: The 10-Q/A is an amendment to the quarterly 10-Q report. It is used to correct or update information that was originally filed in the 10-Q.
   - Investopedia Link: https://www.investopedia.com/terms/1/10-q.asp

5. 8-K
   - Description: The 8-K is used to report major events or corporate changes that are important to shareholders. These events can include mergers, acquisitions, bankruptcy, or changes in executives.
   - Investopedia Link: https://www.investopedia.com/terms/1/8-k.asp

6. 8-K/A
   - Description: The 8-K/A is an amendment to the 8-K report. It is filed to provide additional information or correct information originally reported in an 8-K.
   - Investopedia Link: https://www.investopedia.com/terms/1/8-k.asp

7. DEF 14A
   - Description: The DEF 14A, or Definitive Proxy Statement, provides information about matters to be voted on at a company’s annual meeting, including executive compensation, board nominees, and other significant proposals.
   - Investopedia Link: https://www.investopedia.com/terms/d/definitive-proxy-statement.asp

8. DEF 14A/A
   - Description: The DEF 14A/A is an amendment to the DEF 14A Proxy Statement. It is used to update or correct information originally filed in the DEF 14A.
   - Investopedia Link: https://www.investopedia.com/terms/d/definitive-proxy-statement.asp

9. F-1
   - Description: The F-1 is used by foreign companies seeking to list their shares on U.S. exchanges. It provides information similar to the S-1 but tailored for foreign entities.
   - Investopedia Link: https://www.investopedia.com/terms/f/f-1.asp

10. F-1/A
    - Description: The F-1/A is an amendment to the F-1 registration statement. It is used to update or correct information for foreign companies seeking to list their shares on U.S. exchanges.
    - Investopedia Link: https://www.investopedia.com/terms/f/f-1.asp

11. Form 3
    - Description: Form 3 is used by insiders of a company to report their ownership of the company's securities upon becoming an insider. It is required to be filed within 10 days of becoming an officer, director, or beneficial owner.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-3.asp

12. Form 3/A
    - Description: The Form 3/A is an amendment to the original Form 3 filing. It is used to correct or update information regarding insider ownership.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-3.asp

13. Form 4
    - Description: Form 4 is used to report changes in the holdings of company insiders. It must be filed within two business days of the transaction.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-4.asp

14. Form 4/A
    - Description: The Form 4/A is an amendment to the original Form 4 filing. It is used to correct or update information regarding changes in insider holdings.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-4.asp

15. Form 5
    - Description: Form 5 is an annual report used to disclose transactions that were not reported on Form 4, including certain gifts or changes in ownership.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-5.asp

16. Form 5/A
    - Description: The Form 5/A is an amendment to the original Form 5 filing. It is used to correct or update information about transactions not previously reported.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-5.asp

17. Form ADV
    - Description: Form ADV is filed by investment advisers to register with the SEC and state regulators. It provides details about the adviser’s business, services, and fees.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-adv.asp

18. Form ADV/A
    - Description: Form ADV/A is an amendment to the original Form ADV filing. It is used to update or correct information about investment advisers.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-adv.asp

19. Form D
    - Description: Form D is filed by companies offering securities that are exempt from registration under Regulation D. It includes information about the offering and the issuer.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-d.asp

"""
                break
            elif choice == '2' or choice == 'more sec forms':
                text_content ="""
20. Form D/A
    - Description: Form D/A is an amendment to the original Form D filing. It is used to update or correct information about securities offerings exempt from registration.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-d.asp

21. Form N-1A
    - Description: Form N-1A is used by mutual funds to register with the SEC and provide information to investors about the fund’s investment objectives, strategies, and fees.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-n-1a.asp

22. Form N-1A/A
    - Description: Form N-1A/A is an amendment to the original Form N-1A filing. It is used to update or correct information about mutual funds.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-n-1a.asp

23. Form N-CSR
    - Description: Form N-CSR is filed by registered management investment companies to report their certified shareholder reports and other important financial statements.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-n-csr.asp

24. Form N-CSR/A
    - Description: Form N-CSR/A is an amendment to the original Form N-CSR filing. It is used to update or correct information about certified shareholder reports.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-n-csr.asp

25. Form N-Q
    - Description: Form N-Q is used by investment companies to report their portfolio holdings on a quarterly basis, providing details on the investments and their values.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-n-q.asp

26. Form N-Q/A
    - Description: Form N-Q/A is an amendment to the original Form N-Q filing. It is used to update or correct information about investment company portfolio holdings.
    - Investopedia Link: https://www.investopedia.com/terms/f/form-n-q.asp

27. 13D
    - Description: Schedule 13D is filed by investors who acquire more than 5% of a company's outstanding shares. It includes information about the investor's intentions and background.
    - Investopedia Link: https://www.investopedia.com/terms/s/schedule-13d.asp

28. 13D/A
    - Description: Schedule 13D/A is an amendment to the original Schedule 13D filing. It is used to update or correct information about significant shareholders.
    - Investopedia Link: https://www.investopedia.com/terms/s/schedule-13d.asp

29. 13G
    - Description: Schedule 13G is an alternative to Schedule 13D for investors who acquire more than 5% of a company but do not intend to influence or control the company. It is typically used by passive investors.
    - Investopedia Link: https://www.investopedia.com/terms/s/schedule-13g.asp

30. 13G/A
    - Description: Schedule 13G/A is an amendment to the original Schedule 13G filing. It is used to update or correct information about passive investors who hold more than 5% of a company's shares.
    - Investopedia Link: https://www.investopedia.com/terms/s/schedule-13g.asp

31. 13F
    - Description: Form 13F is filed quarterly by institutional investment managers to disclose their holdings in publicly traded securities. It provides transparency into the investment activities of large institutional investors.
    - Investopedia Link: https://www.investopedia.com/terms/1/13f.asp

32. 13F/A
    - Description: Form 13F/A is an amendment to the original Form 13F filing. It is used to update or correct information regarding institutional investment holdings.
    - Investopedia Link: https://www.investopedia.com/terms/1/13f.asp

33. S-1
    - Description: The S-1 is a registration statement required by the SEC for companies intending to go public through an initial public offering (IPO). It includes detailed information about the company’s business model, financials, and risks.
    - Investopedia Link: https://www.investopedia.com/terms/s/s-1.asp

34. S-1/A
    - Description: The S-1/A is an amendment to the S-1 registration statement. It is used to update or correct information in the original S-1 filing.
    - Investopedia Link: https://www.investopedia.com/terms/s/s-1.asp

35. S-3
    - Description: The S-3 is a simplified registration form used by companies that already have a track record of compliance with SEC reporting requirements. It allows for faster and easier registration of securities for public sale.
    - Investopedia Link: https://www.investopedia.com/terms/s/s-3.asp

36. S-3/A
    - Description: The S-3/A is an amendment to the S-3 registration statement. It is used to update or correct information in the original S-3 filing.
    - Investopedia Link: https://www.investopedia.com/terms/s/s-3.asp

37. S-4
    - Description: The S-4 is used for registration of securities in connection with mergers, acquisitions, and other business combinations. It includes detailed information about the transaction and the companies involved.
    - Investopedia Link: https://www.investopedia.com/terms/s/s-4.asp

38. S-4/A
    - Description: The S-4/A is an amendment to the S-4 registration statement. It is used to update or correct information in the original S-4 filing.
    - Investopedia Link: https://www.investopedia.com/terms/s/s-4.asp

"""
                break
            elif choice == '3' or choice == 'market instruments':
                text_content ="""
Codex of Financial Instruments ver 1.42069

To avoid enslavement by the increasingly sophisticated and total control mechanisms outlined in the financial layers, free humans must adopt a multifaceted strategy that emphasizes education, decentralization, community resilience, regulatory reform, and technological empowerment. These moves collectively aim to empower individuals and communities, ensuring they retain autonomy and prevent the concentration of power that leads to total control.\n

    Education and Awareness: The first line of defense against financial and societal enslavement is widespread education and awareness. People need to be informed about the complex financial instruments and control mechanisms that can potentially be used against them. This includes understanding basic financial literacy, the risks and benefits of various investment products, and the implications of emerging technologies like AI, blockchain, and quantum computing. By demystifying these elements, individuals can make informed decisions and resist manipulative financial practices.\n
    Decentralization of Power: To counteract the concentration of control, promoting decentralized systems is crucial. This can be achieved through the adoption of decentralized financial technologies (DeFi), blockchain, and cryptocurrencies, which reduce reliance on centralized financial institutions and governments. Decentralized systems ensure transparency, enhance security, and empower individuals to manage their assets independently. Furthermore, supporting decentralized governance models can distribute decision-making power more evenly across society, preventing the monopolization of control by a few elites.\n
    Strengthening Community Resilience: Building strong, resilient communities is essential to withstand external pressures and maintain autonomy. This involves fostering local economies through community banking, cooperative businesses, and local investment initiatives. Communities should invest in sustainable practices, such as local food production and renewable energy, to reduce dependency on external systems. Additionally, promoting social cohesion and mutual support networks can help communities collectively resist oppressive measures and support each other in times of crisis.\n
    Advocacy for Regulatory Reform: Ensuring fair and transparent financial markets requires active advocacy for regulatory reforms. Individuals and communities must pressure governments to implement regulations that protect against financial manipulation, ensure corporate accountability, and promote transparency in all financial dealings. Strengthening anti-corruption measures and enhancing oversight of financial institutions can prevent abuses of power and protect the interests of the general public. Effective regulation can also mitigate the risks associated with advanced financial instruments and technologies.\n
    Technological Empowerment: Embracing and harnessing technology in an ethical and controlled manner can empower individuals and communities. Investing in and promoting technologies that enhance privacy, security, and autonomy is critical. This includes using secure communication tools, privacy-focused financial platforms, and ethical AI systems that prioritize human well-being. Additionally, fostering innovation in these areas can create alternatives to the centralized technologies that may be used for control. By being proactive in technological adoption and development, free humans can stay ahead of potential threats and retain their freedom.\n

1. **Level 1 Instruments**
   - **Stocks (Equities)**
     - **Common Stock**: Represents ownership in a company and constitutes a claim on part of the company's profits. Common stockholders typically have voting rights.
       - [Investopedia: Common Stock](https://www.investopedia.com/terms/c/commonstock.asp)\n
     - **Preferred Stock**: A class of ownership with a fixed dividend, usually without voting rights. Preferred stockholders have priority over common stockholders in the event of liquidation.
       - [Investopedia: Preferred Stock](https://www.investopedia.com/terms/p/preferredstock.asp)\n
   - **Government Bonds**
     - **Treasury Bills (T-Bills)**: Short-term government securities with maturities ranging from a few days to one year.
       - [Investopedia: Treasury Bills](https://www.investopedia.com/terms/t/treasurybill.asp)\n
     - **Treasury Notes (T-Notes)**: Government securities with maturities ranging from two to ten years, paying interest every six months.
       - [Investopedia: Treasury Notes](https://www.investopedia.com/terms/t/treasurynote.asp)\n
     - **Treasury Bonds (T-Bonds)**: Long-term government securities with maturities of 20 to 30 years, paying semiannual interest.
       - [Investopedia: Treasury Bonds](https://www.investopedia.com/terms/t/treasurybond.asp)\n
   - **Commodity Futures**: Contracts to buy or sell a commodity at a future date at a price agreed upon today.
     - [Investopedia: Commodity Futures](https://www.investopedia.com/terms/f/futurescontract.asp)\n
   - **Exchange-Traded Funds (ETFs)**: Investment funds traded on stock exchanges, much like stocks.
     - [Investopedia: ETF](https://www.investopedia.com/terms/e/exchange-tradedfund-etf.asp)\n

2. **Level 2 Instruments**
   - **Corporate Bonds**: Debt securities issued by corporations to raise capital. They offer higher yields but come with higher risk compared to government bonds.
     - [Investopedia: Corporate Bonds](https://www.investopedia.com/terms/c/corporate-bond.asp)\n
   - **Municipal Bonds**: Bonds issued by local governments or municipalities. Interest is often tax-exempt.
     - [Investopedia: Municipal Bonds](https://www.investopedia.com/terms/m/municipal-bond.asp)\n
   - **Interest Rate Swaps**: Contracts where parties exchange interest payments based on different interest rates.
     - [Investopedia: Interest Rate Swap](https://www.investopedia.com/terms/i/interestrateswap.asp)\n
   - **Currency Swaps**: Agreements to exchange principal and interest payments in different currencies.
     - [Investopedia: Currency Swap](https://www.investopedia.com/terms/c/currency-swap.asp)\n
   - **Credit Default Swaps (CDS)**: Contracts that provide protection against the default of a borrower.
     - [Investopedia: Credit Default Swap (CDS)](https://www.investopedia.com/terms/c/creditdefaultswap.asp)\n
   - **Money Market Instruments**
     - **Certificates of Deposit (CDs)**: Time deposits offered by banks with a fixed interest rate and maturity date.
       - [Investopedia: Certificate of Deposit (CD)](https://www.investopedia.com/terms/c/certificate-of-deposit.asp)\n
     - **Commercial Paper**: Short-term unsecured promissory notes issued by corporations to raise funds.
       - [Investopedia: Commercial Paper](https://www.investopedia.com/terms/c/commercialpaper.asp)\n
     - **Repurchase Agreements (Repos)**: Short-term borrowing where one party sells securities to another with an agreement to repurchase them at a later date.
       - [Investopedia: Repurchase Agreement (Repo)](https://www.investopedia.com/terms/r/repurchaseagreement.asp)\n
   - **Spot Contracts (Forex)**: Agreements to buy or sell a currency at the current exchange rate with immediate settlement.
     - [Investopedia: Spot Market](https://www.investopedia.com/terms/s/spotmarket.asp)\n
   - **Forward Contracts (Forex)**: Agreements to buy or sell a currency at a specified future date at an agreed-upon rate.
     - [Investopedia: Forward Contract](https://www.investopedia.com/terms/f/forwardcontract.asp)\n

3. **Level 3 Instruments**
   - **Exotic Options**
     - **Barrier Options**: Options that become active or void depending on whether the price of the underlying asset reaches a certain barrier level.
       - [Investopedia: Barrier Option](https://www.investopedia.com/terms/b/barrier-option.asp)\n
     - **Asian Options**: Options where the payoff is determined by the average price of the underlying asset over a certain period.
       - [Investopedia: Asian Option](https://www.investopedia.com/terms/a/asian-option.asp)\n
     - **Binary Options**: Options where the payoff is either a fixed amount or nothing at all, based on whether the underlying asset price is above or below a certain level.
       - [Investopedia: Binary Option](https://www.investopedia.com/terms/b/binaryoption.asp)\n
     - **Digital Options**: Similar to binary options, these offer a fixed payoff if a condition is met at expiration.
       - [Investopedia: Digital Option](https://www.investopedia.com/terms/d/digital-option.asp)\n
     - **Lookback Options**: Options where the payoff is based on the optimal price of the underlying asset over the life of the option.
       - [Investopedia: Lookback Option](https://www.investopedia.com/terms/l/lookback-option.asp)\n
     - **Chooser Options**: Options that give the holder the choice of whether to take a call or put option at a later date.
       - [Investopedia: Chooser Option](https://www.investopedia.com/terms/c/chooser-option.asp)\n
   - **Collateralized Debt Obligations (CDOs)**: Investment vehicles backed by a diversified pool of debt, including loans and bonds. The cash flows from the underlying assets are split into different tranches.
     - [Investopedia: Collateralized Debt Obligation (CDO)](https://www.investopedia.com/terms/c/cdo.asp)\n
   - **Credit-Linked Notes (CLNs)**: Debt instruments where payments are linked to the credit performance of a reference entity.
     - [Investopedia: Credit-Linked Note](https://www.investopedia.com/terms/c/credit-linked-note.asp)\n
   - **Mortgage-Backed Securities (MBS)**: Securities backed by a pool of mortgages. Investors receive payments derived from the underlying mortgage payments.
     - [Investopedia: Mortgage-Backed Securities](https://www.investopedia.com/terms/m/mortgage-backed-securities-mbs.asp)\n
   - **Structured Finance Products**
     - **Asset-Backed Securities (ABS)**: Financial securities backed by a pool of assets, such as loans or receivables.
       - [Investopedia: Asset-Backed Securities](https://www.investopedia.com/terms/a/asset-backed-securities-abs.asp)\n
     - **Collateralized Loan Obligations (CLOs)**: A type of CDO that is backed by a pool of loans, often corporate loans.
       - [Investopedia: Collateralized Loan Obligation (CLO)](https://www.investopedia.com/terms/c/collateralized-loan-obligation-clo.asp)\n
   - **Longevity Swaps**: Contracts where one party pays a fixed amount in exchange for payments based on the longevity of a population or individual.
     - [Investopedia: Longevity Swap](https://www.investopedia.com/terms/l/longevity-swap.asp)\n

4. **Specialty Instruments by Firm**
   - **Salomon Instruments**: Instruments used by Salomon Brothers, including certain types of mortgage-backed securities and structured finance products.
     - [Investopedia: Salomon Brothers](https://www.investopedia.com/terms/s/salomon-brothers.asp)\n
   - **Citi Instruments**: Instruments utilized by Citigroup, including particular types of callable equity-linked notes and complex derivatives.
     - [Investopedia: Citigroup](https://www.investopedia.com/terms/c/citigroup.asp)\n
   - **Lehman Instruments**: Instruments used by Lehman Brothers, including specific types of collateralized debt obligations (CDOs) and bespoke derivatives.
     - [Investopedia: Lehman Brothers](https://www.investopedia.com/terms/l/lehman-brothers.asp)\n
   - **Bear Stearns Instruments**: Instruments utilized by Bear Stearns, including particular types of CDOs and bespoke derivatives.
     - [Investopedia: Bear Stearns](https://www.investopedia.com/terms/b/bear-stearns.asp)\n"""
                break
            elif choice == 'q' or choice == 'quit':
                print("Quitting the program.")
                sys.exit()  # Exit the program
            else:
                print("Invalid choice. Please enter 1, 2, or Q.")

        return text_content

    # Clear the screen before starting the display
    os.system('clear' if os.name != 'nt' else 'cls')

    # Display hardcoded ASCII art
    display_hardcoded_ascii_art()

    # Prompt the user and get the choice
    text_content = prompt_user()

    # Display the selected text content normally
    display_text_normally(text_content)

def compile_urls(zip_directory, idx_file):
    """Compile all URLs from the archives into master.idx."""
    print(f"Compiling URLs from {zip_directory} into {idx_file}.")
    for file in os.listdir(zip_directory):
        if file.endswith('.zip'):
            idx_file_path = extract_idx_from_zip(os.path.join(zip_directory, file))
            remove_top_lines(idx_file_path)
            with open(idx_file_path, 'r') as f:
                content = f.read()
            with open(idx_file, 'a') as master_file:
                master_file.write(content)
            os.remove(idx_file_path)
            print(f"Processed {file}")

def scrape_sec(idx_file, download_directory):
    """Begin scraping the entire SEC."""
    os.makedirs(download_directory, exist_ok=True)
    print(f"Starting SEC scraping from {idx_file} to {download_directory}")

    with open(idx_file, 'r', encoding='utf-8', errors='ignore') as file:
        lines = file.readlines()
    
    urls = [process_line(line) for line in lines if process_line(line) is not None]

    def download_file_task(url):
        return download_file(url, download_directory)
    
    failed_urls = []  # To track failed downloads

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_url = {executor.submit(download_file_task, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            url, success = future.result()
            if not success:
                failed_urls.append(url)
            print(f"Downloaded {url} {'successfully' if success else 'with errors'}")

    print(f"Downloaded {len(urls) - len(failed_urls)} files successfully.")
    if failed_urls:
        print(f"Failed to download {len(failed_urls)} files.")

def sec_processing_pipeline():
    import logging
    BASE_URL = "https://www.sec.gov/Archives/"
    zip_directory = "./sec_archives"
    download_directory = "./edgar"
    log_file = os.path.join(download_directory, "sec_download_log.txt")
    
    # Configure logging to write to a file
    logging.basicConfig(
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename='error_log.txt',  
        filemode='w'  
    )

    # Log an error message
    logging.error("This is an error message")

    def log_progress(message):
        with open(log_file, 'a') as log:
            log.write(f"{datetime.now()}: {message}\n")
        print(message)

    def check_file_size(url):
        """Check the size of the file at the given URL."""
        try:
            headers = {'User-Agent': "anonymous/FORTHELULZ@anonyops.com"}
            response = requests.head(url, headers=headers, timeout=10)
            response.raise_for_status()
            return int(response.headers.get('Content-Length', 0))
        except requests.RequestException as e:
            print(f"Failed to get size for {url}: {e}")
            return None

    def download_file(url, download_directory):
        """Download a file from the given URL, log the download, and compute MD5 hash."""
        try:
            headers = {'User-Agent': "anonymous/FORTHELULZ@anonyops.com"}
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
        
            filename = url.split('/')[-1]
            cik = url.split('/data/')[1].split('/')[0]
            dir_path = os.path.join(download_directory, cik)
            os.makedirs(dir_path, exist_ok=True)
            filepath = os.path.join(dir_path, filename)
        
            if os.path.exists(filepath):
                with open(filepath, 'rb') as file:
                    file_hash = hashlib.md5()
                    while chunk := file.read(8192):
                        file_hash.update(chunk)
                    current_md5 = file_hash.hexdigest()
            
                log_file = os.path.join(download_directory, 'download_log.txt')
                if os.path.exists(log_file):
                    with open(log_file, 'r') as log:
                        for line in log:
                            parts = line.strip().split(',')
                            if len(parts) == 4 and parts[2] == filepath:
                                logged_md5 = parts[3]
                                if current_md5 == logged_md5:
                                    print(f"FILE already downloaded. {current_md5} verified: {filepath}")
                                    return True
    
            with open(filepath, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
        
            with open(filepath, 'rb') as file:
                file_hash = hashlib.md5()
                while chunk := file.read(8192):
                    file_hash.update(chunk)
                md5_hash = file_hash.hexdigest()
        
            log_entry = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{url},{filepath},{md5_hash}\n"
            with open(log_file, 'a') as log:
                log.write(log_entry)
        
            print(f"Downloaded: {filepath}, MD5: {md5_hash}")
            return True
    
        except requests.RequestException as e:
            print(f"Error downloading {url}: {e}")
            return False
        
    def process_line(line):
        parts = line.split('|')
        if len(parts) >= 5:
            filename = parts[4].strip()
            if filename.endswith("Filename"):
                filename = filename.rsplit('/', 1)[0]
            url = f"https://www.sec.gov/Archives/{filename}"
            return url
        return None

    def extract_idx_from_zip(zip_path):
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file_name in zip_ref.namelist():
                if file_name.endswith('.idx'):
                    idx_content = zip_ref.read(file_name).decode('utf-8', errors='ignore')
                    # Split by newline and skip the first 12 lines (assuming headers end at line 12)
                    return '\n'.join(idx_content.split('\n')[12:])
        raise FileNotFoundError("No IDX file found in ZIP archive.")

    def get_user_selection(zip_files):
        print("\nEnter a 4-digit year, 'qtr' for specific quarter, or '0' to return to main menu:")
        while True:
            choice = input("Your choice: ").strip()
            if choice == '0':
                return None
            elif choice == 'qtr':
                print("\nAvailable ZIP files:")
                for i, file in enumerate(zip_files, 1):
                    print(f"{i}. {file}")
                while True:
                    try:
                        choice = int(input("Enter the number of the ZIP file to process (or 0 to exit): "))
                        if choice == 0:
                            break
                        if 1 <= choice <= len(zip_files):
                            return [zip_files[choice - 1]]
                        print("Invalid choice. Please enter a number between 1 and", len(zip_files))
                    except ValueError:
                        print("Please enter a valid number.")
            elif choice.isdigit() and len(choice) == 4:
                year = choice
                print(f"Processing files for year {year}. Enter a quarter (1-4) or press Enter for all quarters:")
                quarter = input("Quarter (or press Enter for all): ").strip()
                if quarter and quarter.isdigit() and 1 <= int(quarter) <= 4:
                    year_files = [f for f in zip_files if f.startswith(year) and f.endswith(f"_QTR{quarter}.zip")]
                else:
                    year_files = [f for f in zip_files if f.startswith(year)]
            
                if year_files:
                    print(f"Processing files for year {year}, quarter {quarter if quarter else 'all'}:")
                    return year_files
                else:
                    print(f"No files found for year {year}, quarter {quarter if quarter else 'all'}.")
            else:
                print("Only 4-digit year format accepted. For example: 1999")

    def process_zip(zip_path):
        """Process a single ZIP file."""
        log_progress(f"Processing {zip_path}")
        idx_content = extract_idx_from_zip(zip_path)
        urls = [process_line(line) for line in idx_content.split('\n') if process_line(line)]
    
        downloaded = 0
        failed = 0
        total_files = len(urls)
    
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(download_file, url, download_directory) for url in urls]
            for future in concurrent.futures.as_completed(futures):
                if future.result():
                    downloaded += 1
                else:
                    failed += 1
                log_progress(f"Downloaded {downloaded}/{total_files}, Failed {failed}")

        log_progress(f"Finished processing {zip_path}. Downloaded {downloaded}/{total_files}, Failed {failed}")

    try:
        os.makedirs(download_directory, exist_ok=True)
        zip_files = [f for f in os.listdir(zip_directory) if f.endswith('.zip')]

        while True:
            selected_zips = get_user_selection(zip_files)
            if not selected_zips:
                break
        
            total_files = sum(len([process_line(line) for line in extract_idx_from_zip(os.path.join(zip_directory, zip)).split('\n') if process_line(line)]) for zip in selected_zips)
        
            for zip_file in selected_zips:
                zip_path = os.path.join(zip_directory, zip_file)
                process_zip(zip_path)

        log_progress("SEC processing pipeline completed.")

    except Exception as e:
        log_progress(f"An error occurred: {e}")

    def remove_top_lines(file_path, lines_to_remove=11):
        """Remove the top `lines_to_remove` lines from the given file."""
        with open(file_path, 'r') as file:
            lines = file.readlines()
        
        with open(file_path, 'w') as file:
            file.writelines(lines[lines_to_remove:])

    def compile_urls(zip_directory, idx_file):
        """Compile all URLs from the archives into master.idx."""
        print(f"Compiling URLs from {zip_directory} into {idx_file}.")
        for file in os.listdir(zip_directory):
            if file.endswith('.zip'):
                idx_file_path = extract_idx_from_zip(os.path.join(zip_directory, file))
                remove_top_lines(idx_file_path)
                with open(idx_file_path, 'r') as f:
                    content = f.read()
                with open(idx_file, 'a') as master_file:
                    master_file.write(content)
                os.remove(idx_file_path)
                print(f"Processed {file}")

    def scrape_sec(idx_file, download_directory):
        """Begin scraping the entire SEC."""
        os.makedirs(download_directory, exist_ok=True)
        print(f"Starting SEC scraping from {idx_file} to {download_directory}")

        with open(idx_file, 'r', encoding='utf-8', errors='ignore') as file:
            lines = file.readlines()
        
        urls = [process_line(line) for line in lines if process_line(line) is not None]

        def download_file_task(url):
            return download_file(url, download_directory)
        
        failed_urls = []  # To track failed downloads

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_url = {executor.submit(download_file_task, url): url for url in urls}
            for future in concurrent.futures.as_completed(future_to_url):
                url, success = future.result()
                if not success:
                    failed_urls.append(url)
                print(f"Downloaded {url} {'successfully' if success else 'with errors'}")

        print(f"Downloaded {len(urls) - len(failed_urls)} files successfully.")
        if failed_urls:
            print(f"Failed to download {len(failed_urls)} files.")

    try:
        # Ensure the master.idx file is empty or create it
        with open(idx_file, 'w') as master_file:
            master_file.write("")  # Clear the file if it exists

        zip_files = [f for f in os.listdir(zip_directory) if f.endswith('.zip')]

        for zip_file in zip_files:
            zip_path = os.path.join(zip_directory, zip_file)
            try:
                print(f"Processing {zip_file}")
                idx_file_path = extract_idx_from_zip(zip_path)
                remove_top_lines(idx_file_path)
                
                with open(idx_file_path, 'r') as f:
                    content = f.read()
                file_queue.put(content)

                os.remove(idx_file_path)
                
                print(f"Successfully processed {zip_file}")
            except Exception as e:
                print(f"Error processing {zip_file}: {e}")

            # Write from the queue to the master.idx file after each zip file
            def write_to_master_file():
                while not file_queue.empty():
                    content = file_queue.get()
                    with open(idx_file, 'a') as master_file:
                        master_file.write(content)

            write_to_master_file()

        print("Compilation complete! uwu")

        # Verbose start of compile_urls and scrape_sec
        print("\nStarting to compile URLs from ZIP files...")
        start_time = time.time()
        compile_urls(zip_directory, idx_file)
        end_time = time.time()
        print(f"URL compilation completed in {end_time - start_time:.2f} seconds.")

        print("\nStarting to scrape SEC data...")
        start_time = time.time()
        scrape_sec(idx_file, download_directory)
        end_time = time.time()
        print(f"SEC scraping completed in {end_time - start_time:.2f} seconds.")

    except Exception as e:
        print(f"An error occurred: {e}")     

def create_game_window(game_name):
    layout = [
        [sg.Text(f"Welcome to {game_name}!")],
        [sg.Button('Play'), sg.Button('Close')]
    ]
    return sg.Window(f"{game_name} Window", layout)

def start_animation(window, frames, key):
    threading.Thread(target=animate_gui, args=(window, frames, key), daemon=True).start()

def parse_gui(search_term, target_directory):
    class MLStripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.reset()
            self.strict = False
            self.convert_charrefs = True
            self.text = []

        def handle_data(self, d):
            self.text.append(d)

        def get_data(self):
            return ''.join(self.text)

    def strip_tags(html):
        s = MLStripper()
        s.feed(html)
        return s.get_data()

    def search_files(directory, pattern):
        files_found = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        if pattern in f.read():
                            files_found.append(file_path)
                except UnicodeDecodeError:
                    continue
        return files_found

    def process_file(file_path, all_texts, all_csv_rows, export_base_dir):
        try:
            print(f"Processing file: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            matches = re.findall(r'<TEXT>(.*?)</TEXT>', content, re.DOTALL)
            if not matches:
                print("No <TEXT> tags found.")
                return

            cleaned_lines = []
            for match in matches:
                lines = match.split('\n')
                for line in lines:
                    clean_line = strip_tags(line).strip()
                    if clean_line:
                        cleaned_lines.append(clean_line)

            if not cleaned_lines:
                print("No clean text extracted after processing.")
                return

            # Prepare for saving
            txt_save_location = os.path.join(export_base_dir, f'{os.path.basename(file_path)}.txt')
            csv_save_location = os.path.join(export_base_dir, f'{os.path.basename(file_path)}.csv')

            # Save to txt file
            with open(txt_save_location, 'a', encoding='utf-8') as txtfile:
                txtfile.write(f"File: {file_path}\n")
                txtfile.writelines(f"{line}\n" for line in cleaned_lines)
                txtfile.write('\n' + '-' * 50 + '\n\n')

            # Save to CSV file
            source_url = 'URL not found'
            source_log_file = file_path.replace('.txt', '-legal-source-log.txt')
            if os.path.exists(source_log_file):
                with open(source_log_file, 'r', encoding='utf-8') as log_file:
                    source_url = log_file.readline().strip()

            text_blocks = [' '.join(cleaned_lines[i:i+50]) for i in range(0, len(cleaned_lines), 50)]
            for block in text_blocks:
                all_csv_rows.append([file_path, source_url, block])

        except Exception as e:
            print(f"Error processing file {file_path}: {e}")

    if not os.path.exists(target_directory):
        print(f"Directory {target_directory} does not exist.")
        return

    files_found = search_files(target_directory, search_term)
    files_found_count = len(files_found)

    all_texts = []
    all_csv_rows = []

    export_base_dir = os.path.abspath(os.path.join(target_directory, '../export', os.path.basename(target_directory)))
    if not os.path.exists(export_base_dir):
        try:
            os.makedirs(export_base_dir)
            print(f"Created directory: {export_base_dir}")
        except OSError as e:
            print(f"Error creating directory {export_base_dir}: {e}")
            return

    for file_path in files_found:
        process_file(file_path, all_texts, all_csv_rows, export_base_dir)

    # Define the final output file names
    txt_final_save_location = os.path.join(export_base_dir, f'{os.path.basename(target_directory)}-{search_term}.txt')
    csv_final_save_location = os.path.join(export_base_dir, f'{os.path.basename(target_directory)}-{search_term}.csv')

    # Write all collected texts to one file
    with open(txt_final_save_location, 'w', encoding='utf-8') as final_txtfile:
        final_txtfile.writelines(all_texts)

    # Write all CSV rows to one file
    with open(csv_final_save_location, 'w', newline='', encoding='utf-8') as final_csvfile:
        csvwriter = csv.writer(final_csvfile)
        # Write header if needed
        csvwriter.writerow(["File Path", "Source URL", "Text Block"])
        csvwriter.writerows(all_csv_rows)

    print(f"\nSearch completed. Results saved to {txt_final_save_location} and {csv_final_save_location}.")
    
    return txt_final_save_location, csv_final_save_location
    
def list_files_in_gui(directory):
    # List all files in the directory, then filter out the specific CSV files
    all_files = os.listdir(directory)
    return [f for f in all_files if (f.endswith('.csv') and f not in {'edgar_CIKs.csv', 'edgar_CIK2.csv'}) or f.endswith('.txt')]

def animate_gui(window, frames, key):
    if key is None or key not in window.AllKeysDict:
        print(f"Warning: Key '{key}' not found in window or is None.")
        return  # or handle this case appropriately

    while True:
        for frame in frames:
            window.write_event_value('-UPDATE_ANIMATION-', (key, frame))  # Send key with the frame
            time.sleep(0.1)

def gui_directories(directory, csv_file):
    try:
        return [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))]
    except Exception as e:
        print(f"Error listing directories in {directory}: {e}")
        return []

def TableSimulation(csv_file_path):
    from concurrent.futures import ThreadPoolExecutor

    # --- Populate table with file contents --- #
    data = []
    header_list = []
    
    if csv_file_path:
        with open(csv_file_path, "r") as infile:
            reader = csv.reader(infile)
            header_list = next(reader)
            data = list(reader)  # read everything else into a list of rows    

    sg.set_options(element_padding=(0, 0))
    right_click_menu = ['', ['View File', 'Download File']]

    layout = [
        [sg.Table(values=data,
                  headings=header_list,
                  max_col_width=30,
                  auto_size_columns=True,
                  justification='right',
                  num_rows=min(len(data), 20),
                  key='-TABLE-',
                  expand_x=True,
                  expand_y=True,
                  enable_events=True,
                  right_click_menu=right_click_menu,
                  col_widths=[100] * len(header_list),
                  select_mode=sg.TABLE_SELECT_MODE_EXTENDED)],
        [sg.Button('Download selected CIK\'s filings', key='-DL-CSV-', size=(25, 2)), sg.Text(' ', size=(15, 2)), sg.Text('OR', size=(15, 2)), sg.Button('Download Everything.', key='-DL-MASS-', size=(25, 2))],
    ]

    window = sg.Window('Resizable Table', layout, finalize=True, resizable=True)
    
    def remove_html_xml_tags(text):
        """Remove HTML and XML tags from the text."""
        soup = BeautifulSoup(text, 'html.parser')
        return soup.get_text()

    def clean_text(text):
        """Remove empty lines from the text."""
        return '\n'.join(line.strip() for line in text.split('\n') if line.strip())

    def handle_events(window):
        base_download_dir = './edgar'

        selected_rows = []
        sort_col = -1
        sort_asc = True

        while True:
            event, values = window.read()
            if event == sg.WIN_CLOSED:
                break
            elif event == '-TABLE-':
                if '-TABLE-' in values and values['-TABLE-']:
                    selected_rows = values['-TABLE-']
                if values['-TABLE-'] and values['-TABLE-'][0] in header_list:
                    col_index = header_list.index(values['-TABLE-'][0])
                    if col_index == sort_col:
                        sort_asc = not sort_asc
                    else:
                        sort_asc = True
                    sort_col = col_index
                    sorted_data = sorted(data, key=lambda x: x[col_index], reverse=not sort_asc)
                    window['-TABLE-'].update(values=sorted_data)
            elif event == 'Download File':  # Right-click menu item selected
                print("Right-click download event triggered")

                if selected_rows:
                    row_index = selected_rows[0]
                    partial_url = data[row_index][4]  # Assuming URL is in the 5th column
                    full_url = f"https://www.sec.gov/Archives/{partial_url}"
                    print(f"Attempting download from full URL: {full_url}")

                    with ThreadPoolExecutor() as executor:
                        future = executor.submit(GUI_DL, full_url)
                        downloaded_file_path = future.result()
                        print("called GUI-DL")
                    if downloaded_file_path:
                            try:
                                # Extract CIK from the URL for directory naming
                                parts = partial_url.split('/')
                                for i, part in enumerate(parts):
                                    if part == 'data' and i + 1 < len(parts):
                                        cik = parts[i + 1]
                                        break
                                # Adjust the file path to remove 'data/' from the directory structure
                                new_path = os.path.join(base_download_dir, cik, os.path.basename(downloaded_file_path))
                                if not os.path.exists(os.path.dirname(new_path)):
                                    os.makedirs(os.path.dirname(new_path))
                                    print(f"Created directory: {os.path.dirname(new_path)}")
                                shutil.move(downloaded_file_path, new_path)
                                print(f"Moved file to: {new_path}")

                                with open(new_path, 'r', encoding='utf-8', errors='ignore') as file:
                                    content = file.read()
                                    cleaned_content = clean_text(remove_html_xml_tags(content))
                                    print("Called clean_text")
                                    sg.popup_scrolled(cleaned_content, title=f"Content of {os.path.basename(new_path)}", size=(80, 30))
                            except Exception as e:
                                sg.popup_error(f"Error reading or moving file: {e}")
                    else:
                        sg.popup_error("Failed to retrieve or determine the downloaded file path.")
            elif event == '-DL-CSV-':
                print("Download event triggered")
                print(f"Selected Rows: {selected_rows}")

                if selected_rows:
                    if len(selected_rows) > 1:  # Multiple selections
                        # Create a temporary CSV with selected CIKs
                        temp_csv = "temp_ciks.csv"
                        try:
                            with open(temp_csv, 'w', newline='') as temp_file:
                                writer = csv.writer(temp_file)
                                writer.writerow(['CIK'])  # Header
                                print("wrote header")
                                for row_index in selected_rows:
                                    writer.writerow([data[row_index][0]])
                            print("wrote rows")
                        except IOError as e:
                            print(f"File operation failed: {e}")
                        # Use the function to download from crawling with the temp CSV
                        download_from_csv(temp_csv)
                        os.remove(temp_csv)  # Clean up temp file
                    else:  # Single selection
                        row_index = selected_rows[0]
                        directory_part = data[row_index][0]
                        sec_url = edgar_url + directory_part
                        with ThreadPoolExecutor() as executor:
                            future = executor.submit(testing, sec_url)
                            result = future.result()
                            print(f"Downloaded filings for: {directory_part}")
            elif event == '-DL-MASS-':
                # Collect all unique CIKs from the first column of your data
                unique_ciks = set(row[0] for row in data)  # Assuming data is your list of rows

                if unique_ciks:
                    # Create a temporary CSV with all unique CIKs
                    temp_csv = "temp_ciks.csv"
                    with open(temp_csv, 'w', newline='') as temp_file:
                        writer = csv.writer(temp_file)
                        writer.writerow(['CIK'])  # Header
                        for cik in unique_ciks:
                            writer.writerow([cik])
        
                    # Use the function to download from crawling with the temp CSV
                    download_from_crawling(temp_csv)
                    os.remove(temp_csv)  # Clean up temp file
                else:
                    sg.popup("No CIKs found in the data.")

    # Call the event handling function
    handle_events(window)

    window.close()
                           
def animate_help(window, frames):
    for frame in frames:
        window['-HELP_ANIMATION-'].update(frame)
        window.refresh()
        time.sleep(0.005)  # Adjust sleep time for animation speed

def show_help():
    # Load your README content
    readme_content =("""The Quest for SEC Scrolls: A Pythonic Adventure

Introduction Welcome, brave adventurer, to the mystical realm of Python, where you shall embark on a quest not for gold or glory, but for knowledge—the arcane scrolls of the SEC. This README shall guide you through the installation of the necessary tools, the setup of your environment, and the execution of your script, all while immersing you in a tale of adventure and discovery.

Prerequisites Before you can begin your quest, ensure your realm (computer) is prepared:

Python: The ancient language of the wise. Download the latest version from python.org. pip: The magical tool for installing additional spells (packages). It comes with Python, but ensure it's up to date by running: bash python -m pip install --upgrade pip

Installation To install the script's dependencies, you'll need to cast the following incantations:

Open your terminal (the portal to the digital realm). Navigate to the directory where you've saved charlie.py: bash cd path/to/your/script Install the required packages with: bash pip install -r requirements.txt

If there's no requirements.txt, you might need to manually install sec-api or any other libraries mentioned in the script.

The Quest Begins Your script, charlie.py, is your map and key to the treasure vaults of SEC knowledge. Here's how to embark:

Run the script from your terminal: bash python charlie.py

The Adventure As you run the script, imagine yourself navigating through ancient libraries, each function a room, each loop a corridor:

Explore Functions: Each function might represent a different chamber or vault where scrolls are kept. Handle Exceptions: These are the traps and puzzles you must solve to proceed. Output: Your treasure, the scrolls of SEC data, revealed in the terminal or saved to files.

The Quest for SEC Scrolls: A GUI Adventure - Step-by-Step Guide

Your Journey Through the GUI Step 1: Begin Your Search Action: Click the Search Button and enter a search term or CIK number. What Happens: Your command sends out a digital hawk to scour the vast digital libraries of the SEC. This might take a moment, but it will create a CSV file cataloging your findings.

Step 2: Choose Your Scroll Action: Select a CSV file from the list provided. What Happens: You're now looking at your catalog of scrolls. Each CSV represents a set of SEC filings or data points you've discovered.

Step 3: Decide How to Retrieve Your Scrolls Option A: Open CSV Button Action: Click this to view the data in a tabular format. What Happens: It's like opening a treasure chest. You get to inspect your loot in detail, seeing exactly what scrolls you've cataloged. Option B: Download CSV/Crawl Buttons From CSV: Choose this to download files directly from URLs listed in your CSV. It's like summoning artifacts by their exact location. From Crawling: Opt for this if you want a more thorough approach. Digital scouts will gather all related scrolls, which might take longer but ensures you get everything.

Step 4: Organize Your Findings Action: Click the Sorted Files Button. What Happens: Before you can use your scrolls, they need organizing. This step sorts and cleans your downloaded files, ensuring they're ready for use. Think of it as organizing your spell components before casting.

By the Adventurer's Code: Remember, while this GUI simplifies your quest, the knowledge you seek must be used wisely. Always ensure your actions comply with local laws and ethical standards. The creator of this script, while guiding you, takes no responsibility for how you choose to use this powerful tool.

uWu May your GUI adventures be filled with discovery.""")

    # Example of ASCII animation
    ascii_animation = [
    """                                                                                                                                                                                                                                             
                                                                                                            &oo""""""W                                                                                                                              
                                                                             bwmwmmwmm                  &""'addbbbbbdkoooW                                                                                                                          
                                             aqmmmmZmq                  kqZmmn(((((((xmmmq*           MokdbbbkbbdbbbkbbbbkoM                                                                                                                        
              qqqwwwwmq                  awZZU/(|((||/XZZm            bwmj1)((((|((|(((((fQwh       &oabbbmzYYXmbdbdddd0JUXUaM              bO00000000mq                                                                                            
         qmmZ0||||||||cwwwp            hOx/|||((|||||||(||vqb       kZ0t((([?-?1(()((((1?--[Cmh    %abkbmz)*``;/cZbbdCv?^`^inC          ZZOZn~<<<<<<<<~JZZZm                                                                                        
       ZZ0||/|//|||(||||/|nZq        hZf/||(-_?}|((|||||1--?xmh     0j|((]-:```l?{(((1?<^^**~[U    %odddu,^`,~++[Ldbb)*^^I~++|o      amQ[><>>>>>>>><><><>><xQZ                                                                                      
     wmC|/||}]~[/||((|||}_--(Oq     of//|1+:```,+]|((|[<l``^l-c     kt)(1l`*^!___[(((?```,~++-Y   #akbddc*^`ihW&Mbddd)*`*]M&W&*M    wY-<>>>>>i>>>>>>>>>><<><>f00                                                                                    
     /|||([?^^`^?[(|||}?!```,_1w    of||(l*`^,<+>?)(((<```!+++X   aZC/((1I`*^YW&8Q)()?^``<a&&WmZd%hpbdddY_i*IXJbabdbbc_;^<UUahbb&  Y?<<<>>>i>>>>>>>>>>><><<>~}xu                                                                                    
     Q|(|1*```ii>~)(|(>^`^:~+<_Q   hL/|||]^``}&&Whx|((>``*z&&&owh%df(||()_l*`/YQQz|)({~l*IcQLCf)d8hpbdbbddU?-_}Zbdbbbbpr_+_fpddb&#ZU_<><>i>>>>>>>>><<<><<|rrru                                                                                      
   ZOY|(|1^`*,M&8#j|(|>```-hW&Ww0 at/||||)~:^~JQOLf|(|[>^^{L00X/X wj|((((()<;;I[|(()((({!I<<})((0%apdbbbbbbdbdbbbdbbbbbbbbbbbbbb8U_>><>>>>i>>>>>><>><])]|Q                                                                                          
  %X|(||()I;`,YL0Ct|||+I,`iXQCU/tha/((|||||1+++-)||||(|(}++_[|||X%q|(|(()()((((((((((((((((()(()0%hdbbbbbdbdbbbdbdbbbbbbbbbbbbbbWU_>>>>>>>>>>i>><}{}1UQ0Q0            QQ0O            0000O            ZZZ0Zw           ZU0QOq           mzzQO      
  %X(||||||(iII!)||//|||]lIl~(//faht|(|||||||/||||||||||||||||||Y%q|(((((((((((((|(((((((((()(((0%hdbbdhbdbddbdpqqpdbbbbbpbpbbbb&U_<>>>>>>>>>>>>?ZwwQ;**`;           b,..*k           I^``:b           -**`ic           +..*1U           r```|      
  %X(||||(|(|(|||||||/|||/||||||fhot|((|||||||||||||||||||||||||X Q||||vn()()|(xzzXn(((((/zv/(()O%addpa #dpddbba  abbbddph8Mpdkb8Y_>>>>>>>>i>i>>i>>>i;::;l            <!i<            ]~>>_            [!ii-J           |!!itJ           niiij      
  %X(|||||(|||||||///|||||/||||/taat|||fcj//|||jJQLY|||||/vCt|||X Q(tYCdqQv|()(L   Q)|(tYLbbQzj(0 apo     *dppdo  *bppda&    #bb q1[~>>>>>>>>>i>>>>>>>>><nZZZq                                                                                      
  %X|||jYz//|(|/YXYYf|||||tun//|fhot(nz#8OCx||/xL  Mc||tzJp8oLr|X wzQb     OUJJb   pXUU0d    OLYq                                  U[i>>>>i>i>>i>i>i>>>>>>>><fOO                                                                                    
  %Y|rzL&aYc/||tW  Mr|||fcQozXc/fhMQO&    MLzUfXw  bCXJcd     bu0                                                                  mf]~>>>>>>i>>i>>>>>>>>>>>>+][                                                                                    
   zzX     8YYYU   &XzzcOk    XYJo                                                                                                   wf?_>>i>>>>>i>>>>>>>i>+]{                                                                                      
                                                                                                                                       Ov[[}->>i>i>i>i<?}}{u                                                                                        
                                                                                                                                            w1{}}}}{[}1 """,                                                                                        
    """                                                                                                                                                                                                                                             
                                                                             bwmwmmwmm                      8oo""""""W                                                                                                                              
                                             aqmmmmZmq                  kqZmmn(((((((xmmmq*             &""'adbbbbbbdboooW                                                                                                                          
              qqqwwwwmq                  awZZU/(|((||/XZZm            bmwf))((((|(|((((((fQwh         Makdbbkbbdbbbkbbkbbka#                bO0000000Omp                                                                                            
         qmmZ0||||||||cwwwp            hOx/||/((|||||||(||vmh       kZ0t((([--?1(()((((1?--[Cmh     WoabbbmzYXYmbddddddLzzcXaM          ZZOZn~<<<<<>>>+JZZZm                                                                                        
       ZZ0||/|//|||(|||/|/nZq        hZf/|((--?}|((|(|||{?-?xmh     0j|((]-:^``l?{(((1?<^^**~[U    %abbbmz)*``;tcZbbdJv?^`^!nC       amQ[><>>>>>>><>>><>><>nQZ                                                                                      
     wmC|/||[]+[/||(||||}_--(Oq     of//|{+;```*_](((|}_!```i-c     kt)(1l`*`i___[(((?```,~++-Y    8hdddu*``,~++]Ldbb)*^^l~++|o     wY-<>>>>>i>>>>>><><<><<>>fOO                                                                                    
     /|||([?^``^?[(|||}?l```,+1w    of||(I`*`,+_>])(((<``*i_++X   aZC/(|1I`*^YW&8Q)()?^``<a&&WmZd M*hdbdz*``ihW&Mkddd)*`*?M&W&*M   Y?<<<>>>i>>>>>>><><><>>><><<_                                                                                    
     Q|((1^```<~+_)((|>^^^:~-_[w   hL/|||_``^}&&Whx|(|>``^u8&&owh%q/(|(()+l`*(U0Lz)(({~l*IcQLCf)q8hpddddJ_i*IXJbabdbbv-I^<JChhbb8#ZU_<>>>i>>>>>>>>><><>>>>><<>>(LZ                                                                                  
   ZOY||(1^``,M&&Mj|||>```-a&&Ww0 hf|/|||)_;`<JLOLj(|([>*`{UQ0Y|X mt(((((()~I!i[()())(({!I<<})((08apbbbdddU?-_}Zbdbbkbpr___fpddb&U_>><>>>>>>>>i>>>>>><>><>>>><><<}                                                                                  
  %X|(|||)I;`,YLOJt|||+I,*iXQCU/tha/|(|||||1+++-(|(||||(}++_[|||X%q|((((((((((((()(((((((((()(()0%hdbbbbbbdbdddddddbdbdbbbbbbkbbWU_<>>>>>>>>>>>>>>>>>>>>>><><><>>?LZ            0QOQO            OZOZO            0O00O           d000Om           w
  %X(|||(||(iIIl((|//|||]lIl~(//faa/(((||||||/|||(|(|(||||||||||Y%q(()((((||((((((((((((((((()()0%adbbbbbbbdbbdbdbbbbbbbbbbbbbbb&Y_<>>>>><>>>>><>><>><>><>>><><>>I`I            ;""',            *.*`(            >..*z           ?I*`*f           r
  %X(|||||(|(|||(||||/||//||((||fhot|(|||||||||||(|||((||||||||/X Q|(((|(|(nz|)((((((fXn|(((((((0%hdbbbdbdbppddbdbbbbpbpbbbbbbkb&U_>>>>>>>>>><>>>>>>>>>>>>>>>><><<>+            ?>i>+            +~>ir            1!!>J           (]ii!c           n
  %X(|||(|||(|||||||/||/||/||||/taat||(|(||jXu|(||||(/cX||||||||X Qff()(|vzw Lz|(((jxU kUv/(((rnO%adbbbddpk adpbbbddpa%adbbbbbpdWp1[~>>>>>>>>>>><>><>><>>>>>>>>+?1                                                                                  
  %Y|(|(|||tXX/|||||(|jvj//|/||/fhWUt(||/jvJ@*cv/|/tccp8mJ/|//frC   0xjfrd     0ccvQ     pvzucO     #dppo     #dppdo8    #qbdb     J[i>>>>>>>>>>>>>>>>>>>>>>>>!{a                                                                                   
   zXu//|tcY&8XX/|||fXw YXu/||tvc*  &OxXva     hYJnub     hcccq                                                                    m/]~>>>i>i>i>i>>>>>>>>>>>>_]}                                                                                    
     UYXYU     8Ycnzb     zcvzY#                                                                                                     wf?_>>>>>>>>>>>>>>>>i>+]{                                                                                      
                                                                                                                                       Ov[[}->>i>i>i>>>?}}{n                                                                                        
                                                                                                                                            w1{}{}}{[}1| """,                                                                                       
    """                                                                                                                                                                                                                                             
                                                                             bwmwmmwmm                                                                                                                                                              
                                             owwmmZmZq                  kqZmmn(((((((xmmmq*                 &#""""""*W                                                                                                                              
              qqqwwwwmq                  awZZU/|((|||/XZZm            bwmj1)((((|(|((((((fQwh           &###obbbbbbbdboooW                  bO00000000mq                                                                                            
         qmmZ0||||||||cwwwp            hOx/|/|((||||||||(|cwb       kZ0t((([?-?1(()((((1?--[Cmh       MakddbkbbdbbbkbbkbbkaM            ZZOZn~<<<<<>><~CZZZm                                                                                        
       ZZ0||/|//|||(|||/|/nZq        hZf/|((--?}|((((|||1--?nZa     0j|((]-:```l?{(((1?<^^**~[U     &*abbbZUYXUqbbbdbddLzzcXaM       amQ[><>>>>>>>>>><<>>><xQZ                                                                                      
     wmC|/||[]_]/||(||||}_--(Oq     of//|{+;```*+?(|(|[_l```!?v     kt)(1l`*^!___[(((?```,~++-Y    %abbbmz)*^`:(n0bbpUu?^`^!nC      wY-<>>>>>i>>>>>>>>>><<><>f00                                                                                    
     /|||([?^``^?[)|||}?!```,+1w    of||(I`*^,_++])(((<```i_++X   hZC/((1I`*^YW&8Q)()?^``<a&&WmZp  %adddu*^`*_-?{Qdbb),^^l~++|*    Y?<<<>>>i>>>>>>>>>>><>><<>[xu                                                                                    
     Q|((1^`*^<~~-)|((>^`^:~_-]w   hL/|||_```{&&Whr|((<``*z&&&oOb O((|(|1_l``/C0Lz)((}>:*lzQLCf)O M*hdddz^``ih&&Mkddd)*`*?M&W&*M hZU-<>>>i>>>>>>>>><<><>~|jrru                                                                                      
   ZOY||(1^``,#8&Mj(||<``*-aW&&w0 at/||||)_;`<JLOLj|(|]<^`1L00X|X 0/(((((()<;;l]()()((({!Ili})((w8apddddQ{>*lXJdobdbbv?;^>cLhhdbWJ_>>><>>>>>>>i><><><?)]|Q                                                                                          
  %X|(|||)II`,YL0Ct/||_I,`iXQCU/thht((|||||1+++-(|(||(|(}+++}||/X Q|(|(()((((((|((((((()|((|((()0%hdbbbbddU?__}Zbdbbbbpr___fpdbbWU+<>>>>>>>i>>>><}{{t    0Q0QO            CLJJC            LCCC            OUXYCm           qUYYLw           wLQC0d 
  %X(|||(||)iII!)(||/|||]lIl~(|/faat|(|||||||||||(||||||||||||||Y Q|(((((()((((((|((((((((|(((((0%hdbbbbbbddbddddbbbbbdbbbbbbbbbWU_<>>>>>>i>>>>>?ZwZZ   h<""';            ;""'v            :*^*z           +:^*,n           -``*;f           j```?z 
  %X(||||(||(|||||/||/|//|/|(||/taot|(||||||/|||||||||||||||||||X Q|(||vx|)()|(xzzXn(((((/zv/(((0%hdbdbbbdbddbbbbbbbbbbbbbbbbbbb8U+>>>>>>>>>i>i>>>>><J0OJ[>~>~            >i!ix            >i!iQ           |_li+O           )iii_c           nlii(J 
  %X(|||||(|(|(||||//|||||||||||faat|||tcj/||||jJQQY|||||/vJ//||Y Q(tzJpqQv|)()L   Q(((/cJdbQzj(0%hdbbdkbbbdbbdppqpdbbbbbddddbbk8d1[+>>>>i>>>i>>i>>>>>>><nOOZm                                                                                      
  %Y|||jXz/||||/JUUUf|||||tcu//|fhot|xY#8mLx|//xL  Mc||tzJdWkCj|z wzQb     OUUUd   OvYYCm    OLYq hddpa8#pppddkW  hkbdbdph&Mddbb&  Y[ii>>>i>>>>>>>>i>>><>>>><fOO                                                                                    
  %X|rzL8#XX//|tW  #r|||fX0oJYc/fhMQ08    #LuXjUd  bLUJcd     pnO                                 apo     #dppb#  Mkpdpa&    Mdb   mf]~<>>>>i>i>i>>>>>>>>>>i>+?[                                                                                    
   zzX     &UXYU   &JYYUmo    XYJo                                                                                                   wf-_>>>>>>>>>>>>>>>i>>+]{                                                                                      
                                                                                                                                       Zv[[[?>>i>i>i>>>?}}{u                                                                                        
                                                                                                                                            w1}{}}{}}[)| """,                                                                                       
    """                                                                                                                                                                                                                                             
                                             owwmmmZmq                                                                                                                                                                                              
              wZZZZZZmq                  owmOJ||((|||/XOZm                   dCCCCCCCO                                                                                                                                                              
         qmmZ0|/||((||cmwwp            hOx/|/|((((|||(||(|vqb           kqmZmn((((((|xZmmqo                 &#""""""*W                      dOOO000000mq                                                                                            
       ZZ0||/|/|||||(||///nZq        hZf/||1?-?}|((((|||1--?xZd       bwmj1(((|((((((((((f0qa           &###obbbbbbbdboa*W              mZZZn~<><>>>><~Jmq                                                                                          
     wmC|/||[[_]|/(|(|||{???|Zq     of/||{_!```*+](((|[_l``^!-c     kZ0t((([--?{|)((()(1---[Cma       Makddbbbbbdbkbbbkbbka#         aq0}>>>>>i>>>>>><<><U                                                                                          
     /|||([?^``^?[(|||}?!``*,~}Z    of||(I**`,_+~?)||(<```i_++n     0f|((]-:^``l?{(((1?<*`*^~[Y     &*abbbmUYYYqbbdbdddQzzcXoW      wY->>>>>i>>>>>>><>~|nn                                                                                          
     Q|(|1^`*^<~~_)(|(>^`^,~__]w   kL/||(i^``{&&&ax|((<``*c&&&omd   kt((1l`*`!+++]))(?```,~++-Y    %abdbwU/*``;/cZbbdCv]*`*!uC     Y?<<>>>>>>>>>>>><~nvb                                                                                            
   ZOY|(|1^``,M8&Mj|||~```?aW&&wQ ht/||||?~:^~cY0Lj|(|]>^`1XQ0X/X hZC/((1I`*^YW&&Q()(?^``<a&8WmZp  %adddv*``*~~-[Ldbb)*^^I~_+/*  aZU-><>>>>>>>>>>>~[j                                                                                               
  %X|(||()I;`*XL0Qt|/|_l:^>YQ0C/fhat((|||||1++_?)|||||||}+++[|||X Q(((|()-i^`/C0Qz)(){i;*lzQLCt)O M*hdddz^^`ih&WMbddd)*`*]M&&8*a U_>><>>>>i>i>i><~|*                                                                                                
  %X(||||||(>II!((|//|||]lII<1|/fha/|((|(||||||||||||||(||||||||Y Q|(((((((+:Ii}))((((({!I;>}(((O8apddddY?>*lXCbobdbbu?I^>JLkhdbWU_>>>>>>>>>>>~}x #0Q00O           QLJO0            OZOOO            OLQ0J            00O0m            Z0QCm        
  %X(|||(||(|||||/||||/|//||(|||faa/|||(||||(||||/||||||/|(/||||X Q|((((|((|(((|(|((((()((|(|(((0%hdbbbdbdY?__}Zbdbbbbdn-_-fpbbbWY_><>>>>>>>i<[Om h:*`*;           m**`,            :`*`;d           !`**_c           +*``(            )```j        
  %X|(|||(|(|||||||/|/||||||(|||faat||||((|rUu/||||||/zU/||||(||X Q|||(((|(((|)((((|((((((((((((0%hdbbbbbbdbddbdbdbbbbbbbbbbbbbb8U+>>>>>>>i>>>><_CC~>~<~           ~~<i+            _<>i-d           }li>(Q           /iiij            t!iiz        
  %X|||(|||/cct|||/|||xXx||||||/taWOJt|||jYp%Mmz|(//zOp8qJt||/nX0%p|(|(|(||vYt((|((((fvx((((((((0%hdbbdbbddbbbdbdbbbbbbbbbbbbbbk8d)[~i>>>>>>>>i>><<Y0                                                                                               
   zXu//|tzU8&YXt/||uYC8Jzn|||tvJ#  &OuJva     mUCvYh    %kCJcm   wXx((((ucq qUr||(fUZ pUc/(||uzw%kdbbbdbbbppdbbdbbbbpddbbbbbbbb&  Y[i>i>>i>>>>>>>>>~0pq                                                                                            
     UYXXX     8YYYYk     YXvzY#                                    pJUUJq     pYUYO     hJYUYd   adbbbbdpb8#dpdbbddpo8*ddbbbbdb   mf]~<>>>>i>>>>>>>>><Xqd                                                                                          
                                                                                                    Mdpph8    *kbkbo8    #ddpb&      wt?_>>>>>>>i>>>>>>i~C                                                                                          
                                                                                                                                       Zv[[[?>i>>iiii><-}1                                                                                          
                                                                                                                                            w1{}}{}{}[)| """,                                                                                       
    """                                                                                                                                                                                                                                             
              wZZZZZZmq                      aqwmmZmZq                                                                                                                                                                                              
         qmmZ0|/||((||cmwwp              awZOU||((|||/XZZZ                   bwmwmZZOw                                                      bOOO000000mq                                                                                            
       ZZ0||/|/|||||(||///nZq          hOx/|//((((|||((|(|cqb           kqmZmn(((((((xZmmqo                 &**oooooaM                  mZZZn~<><>>>><~CZZZm                                                                                        
     wmC|/||[[_]|/(|(|||{???|Zq      hZf/|((---}|(((((||1--?xmh       bwmj1(((|((((|(((((fOqa            aoohbbbbbbbdbaooW           aq0}>>>>>>>>>>>><<>>><xQZ                                                                                      
     /|||([?^``^?[(|||}?!``*,~}Z    of/||{+;```,+](((|}_l```!?v     kZ0t((([--?{|)()(((1-_-[Cmh       WahddbbbbddbbbdbbbbkoM        wY->>>>>>>>i>>>>>>>>><><>f00                                                                                    
     Q|(|1^`*^<~~_)(|(>^`^,~__]w    of||(l*``,~+>?)|((>```i_++n     0f|((]-:^*`l-{((({-<^`**~[U     &*abbbmJYYJwdbbddddQUUYJ*&     Y?<<>>>>>i>>>>>>>>>>><><<>[xu                                                                                    
   ZOY|(|1^``,M8&Mj|||~```?aW&&wQ  hL/||(<```{&&Whx|((<``^u8&&omd   kt((1l`*`!~<~?)))?^``*>~+-Y    %abddwCt*``;jYZdbdQY}*`^>vL   hZJ_><>>>i>>>>>>>>><><<<|rrru                                                                                      
  %X|(||()I;`*XL0Qt|/|_l:^>YQ0C/fhhf|/|||)~;`+JQOLf|(|]<^`1L00X/X hZC/((1I``^YW&&0)((?^^`<a&8WmZp  %adddz*^`,<<~?Ldbb)*^^:i>>)M  U_>><>>>>>>>>i>><>><_[[1L                                                                                          
  %X(||||||(iII!((|/||||]lII<1||faa/(|(||||{++~+(||||(|([~~+[|||X Q|(((()<:``/CQQz)((}l,*!XLLJf)O M*hdddc*``ihW&Mbddd)*`*]M&&&#o J_>>>>>>>i>i>>>~}{{t          LCL0O            OZOQO            OZOZO            0O00w           d000Ow           O
  %X||||(|(|||||||||/|/|//||(|||faa/|(|(|||||||||(|||||||(|||||/X Q((((((()<,:l]()(((((}!,:i}(((0%apddddX?>*lXQhobdbdx+;^<JJkhdbWU_><>>>>>>>>>><-ZwmZ          f^*`:            :*:z,            :*``(            >.``z           ?I*`*j           r
  %X((||||(|(|(|||//|||||||||||/faat||(|||||||||||||||||||||||||Y Q|||((((|((((((((((((((|((((|)0%hdbbbbddU?__}Zbdbbbbdu-_-)pdbb&U_>>>>>>>>>>i>>>>>><JOOmq     +~>i_            +<>i_            ~~i>j            )!iiL           (]ii!c           v
  %X||/fYX/||||/JXXXf|||||tux|||faat|(|tn/|||||jJQLY|||||/vJt|||Y Q|(((|(((((|((|(|(((((((((((((0%hdbbbbbbddbdddbdbbbbbbbbbbbbbk8d1[~>>>>>>>>>>i>>>>>>>><nOOZm                                                                                      
  %Y|rzC&oYXt||tW  #r|||tX0oXYc/fhot(uY#8wLx/|/xC  Wc|(/nxm&aLj|z%q|(||vu|()(((xzzzn(((((/zc/(((0%hdbdbbbdbddbbbbbbbbbbbbbbbbbkb8  Y[i>>>i>i>>>>>>>>>>><>>>><fOO                                                                                    
   zcX     &YYXX    CJJJwo    XYJoW0w8    #LuXrJb  bJzYvb     knO Q(tzJppLv|(()L   Q((||vYddLcf(0%hdbbdkbbbdbbdppppdbbbbbpdpdbbb8  mf]~>>>>>>i>i>>>>>>>>>>>i>+?[                                                                                    
                                                                  pnLb     YrxnO   OfucUd    OXxm hddpa8#pppddkW  hkbbbbph8Mdbbb8    wf?_<>>>>>>>i>>>>>>ii>_]{                                                                                      
                                                                                                  apo     #bddb#  Mkddpa&    Mdd       Ov[[[->>i>i>i>i<?}}{n                                                                                        
                                                                                                                                            w1{}{}}{[}1| """,                                                                                       
"""                                                                                                                                                                                                                                                 
              wZZZZZZmq                                                                                                                                                                                                                             
         qmmZ0|/||((||cmwwp                  aqwmmZmZq                                                                                      bOOO000000mq                                                                                            
       ZZ0||/|/|||||(||///nZq            hwZOU/((||||/XZZZ                   bwmwmZZOw                                                  mZZZn~<>>>>>><~CZZZm                                                                                        
     wmC|/||[[_]|/|(||||{???|Zq        hLj/|/|(((|(||((|(|cqb           kpmZmn(((((((xZmmqo                 &**oooooaM               aq0}>>>>>>>>>>>><<>>><xQZ                                                                                      
     /|||([?^``^?[)|||}?!``*,~}Z     bOf|||1?-?}|(((((||1--?xZq       bmmf1((((((((|(((((tOqa            aoohbbbbbbbdbaaoW          wY->>>>>>>>>>>>><>><<<><~fLZ                                                                                    
     Q|(|1^`*^<~~_)|(|>^``:~__]w    *f(/|{_i```*+]|(||[_!``^!-c     bZ0t)(([--?{|()((((1---[CZk       WahddbbbbbdbbbdbbbbkoM       Y?<<>>>>>i>i>>>>>>>>>><><<><+                                                                                    
   ZOY|(|1^``,M8&Mj|||<```?h&&Ww0   af/|(I"*"*+~+-)(((<``*i_++n     qt|((?_,^``l?{((({-<^`*^~[Y     &*abbbmJYYJmbdbdbdpQUUYJ*&   hZJ_><>>>i>>>>>>>>><>><<>>>>>>)QZ                                                                                  
  %X|(||()I;`*XL0Qt|/|_l:^>UQQL/th kL/||(>```{&W&pf|((<``^v8&&oZd   w/)({I`*`l<~<?)))?^``*>~+-Y    %abddwJf^^`;jXmdbdQY}*`^>vL   J_>><>>>>>>>>>>>><>>>>>>>>>>><>>?                                                                                  
  %X(||||||(iII!((|/|/||]lII<1|/fha/((|||[>,`~JQOCj(||]>^^fLQ0X/X bZC/((1I*``YW&&0)((-^^`<a&8&dmd  %adddz,``,<<~?Qdbd(*^^l-++/   U+<>>>>>>>>>>>>>>>>><>>>>>><<><<?        CLQQO            ZZZOb           O0Z0Oq           0O00Ow           00LCOq 
  %X||||(|(||||||||||||/|/||(|||faa/|(||||(]++~_)||||(||]<<+[|||X%Z((|(()<:``/CQQz))({l,*!XQCCt)O #*kdddc,``ihW&Mbddd)*``]M&&&*# J_>>>>>>>>>>>>>>>><>>>><><>><><<?        ;**^,            *``^z           _:*`^X           _.`*Ij           j`*`]z 
  %X(|||(||(|||||||//|||/||||(|/tao/|||||||||||||(|||||||||||||/X%Z|(((((()<::l]()((((){!::!{(((0%hdbbddY?>*lXJbabddbx+;^<J0ahbd8U+>>>>>>>>>>>>><>>>>><>>>>>>>>><?        +<i<_            ~<i>Q           /-!iiO           t_~~?c           v!ll)U 
  %X(||||||/cc/|/||||/xvj/||||||faat|(||||||||||||(|||||||||||||X%Z((|((((|((((((((|(((((|((((((08adkbbbbdU?_-{Zbdbbbbdu-_-jpbbk8p)[+>>>>>>>>><>>><>>>>>>><>>>>+-1                                                                                  
   zXu//|tzU8&YXt|||fYw XXx(|||nz*at|||(|(|fuj/||||||/nv/|||||(|X%0|(()(((((|((((|((((((((((((()0%hdbbbbbbbbbbbbbbbbbbbbbbbbbbbb8  Y]i>>>>i>>>>>>>>>>>>>>>>>>i>)a                                                                                   
     UYXXX     8YYYJb     LUzYJ#  MLc(((|ttOWpxf|||//rO8L||/(|/z0%Z|)))((|(uz/(((((((|rj|(((((()0%hdbbbbbbdbbbbbbbbbbbbbbbbdbbbb8  mf]~>>>>>>>i>>>>>>>>>>>>>>_?[                                                                                    
                                    &UrrcC     wjvjnp    %krfrm   Orj((()/jp U/((((|jY pux/((|ncq8hdbdbbbbdpbdbbbbbkbdbddbbbbbbb&    wf?_>>>>>>>i>i>>>>>>i>+]{                                                                                      
                                                                    Zx/|j0     L(((J     Lr///O   hdbbbddpb&Wddbbkbdqk adbbbbbdb       Ov}[[->>i>i>>i><?}}{u                                                                                        
                                                                                                    *qpddW    Wbdppa     Mdddb              w1{}{}}}}}1| """,                                                                                       
    """                                                                                                                                                                                                                                             
                                                                                                                                            bOOO00OOOOmq                                                                                            
                                                                                                                                        Z0OOx~<>>>>>><~JZw                                                                                          
              wZZZZZZmq                                                                                     W*ooooooaM               amQ]>>>>>>>>>>>>>>>~J                                                                                          
         qmmZ0|/||(|||zZZmp                  oqwmmZmmq                       bZZmmZZOw                   *o*hbbddbbbdbaao&          wY-<>>>>>>>>>>>>>></xn                                                                                          
       ZZ0|||/||/||(||||//nOq            awZOz|(|||||/XZZq              kqZmZx(((((((xZmmqo           WakddbbbbdbbbbdbbbbkoW       Y?<<>>i>>>i>>>><<+fxn                                                                                            
     wZC||||[[_]|/|(||||{???(Ow        hOr/|/|(((||/||||(|vwd         bmmj1)(|(((((((((((tOqa       &oabbbmUYXUqbbbdddpQUUYY*&   hZJ_<>>>>>>>>>>>i>(jo                                                                                              
     t|(|([?^``^?](|(|1]>```,~}Z     aZf/||1?--}||(((((|{--?nmh     kZQt)(){??-{|)))((({---[Cma    %adddwJt*^`IrYmbbdLY}*`^>cQ   U_>>><>>>>>>i>>+]j                                                                                                 
     /|||1*`*^<+~-)(||~```:<-_[w    of|/|)_i`*`,~]|(|([+I```!?X     dt|((]?:```l?1((({-<^`*^<]U    %adddz,^`,<>~-Qdbd(,^^I~++f*  U+>>>>>>>>i>>+}j            QLQQO            OZO0O            0QZZw            LOOOq           CJCLLQ           OC0
   oaL|||1^``:M8&Mj/||~```?o&&Wpb   of/||<``**__+?(|((<`^*!_~+u     dt)(1I`*`l~~~](()?^``*>~_-X   #*kdbdc,``iaW&Mbddd)*`*]#W&&o# U+>>>>>>>>>><[0m           d{`*`:            ;*``{d           :*``u            !``^U           +:`*^x           j""
  *X|||||)I;`*zL0J/|||+I,^~UQ0L/th kL/||(l^``{&&Wwt|((>`*^uW&&aZw MdC|(({;*`^UWW&0)()?^``<a&8WmOp8apbbddY?>*lXCboddddr+;^>JQhhdh U_><>>>>>>>>>>>-JO          _<>>+            +>>i1q           _!i~X            -i<<L           t?ii>X           U<>
  %X((|((||(lII!(||//|||]lII<)(/fhot/(|||}_;`_LC0Xt(||[>*^)L00X|X80(((((1<:^`t0OQz(((}I,*!XLLLf)O%hdbbbbdbU]--}Zbbbbbddu-_?/dbbd8q{?~>>>>>>i>>>>>>-JZ                                                                                               
  %X(||||||(|(|(|||||/|((|((((||fha/|||/|||[:;i~)((||(|(-:;<}|||U%m((((((()<::l[((((((({l::l{)((0%hdbbbdbbdbdddbdbbbbbdbbbbbbbbb8  Y[i>>>i>>>>>>>>>>-JZm                                                                                            
  %X|(||||||||||(|||/|||||||(|||fh*f||||||||||||||||||(|((||||||J%m((((|((|(|(|(|((|((((((((((()08hdbbdbbdbbdbbbbbbbbbbbbbbdbdbb8  mf]~>>>>>>i>i>>>>>>~UOO                                                                                          
  %Y|||||||/YX/|/|||||fXr/||(|||jha/(||||||(|(|||||||||/|/||||||U8m)(||(|(((((((((((|(((((|(|(((0%hdbdbbbbdpdbbbbbbbbpbddbbbbbbb&    wf?_<>>>>>>>>>>>>>>~c                                                                                          
   zXv/||tXJ8&JY/|||jYw XYn/|||nzao/|(|||||//|//|||(||t//|||||(|J%m((((((((||((((((((|))|(((((((0%apdpbbdpb%Mddbkbkdpk *kbbbbddb       Ov[[[->>i>i>>>><?[{                                                                                          
     UUUUJ     8UYYUb     UzvzY*  #Xj(((|ttZ#mjt||(/trm8L|(|(|t/C Cx/(())/rp U/((((|jY Ort((((ttQ  8*bdqa     Mbpdp*8    #pddb              w1{}}{}}}[)|                                                                                            
                                    WXj/ru     aX/tnp    &hxfxO     mzj|tO     Q||(J     Lr///O """,                                                                                                                                                
"""                                                                                                                                                                                                                                                    
                                                                                                                                            bOOO00OOO0mp                                                                                            
                                                                                                            W*ooooooaM                  Z0OOx~<>><>>><-JZZZm                                                                                        
                                                                             bZZmmZZOw                   oaohbbbbbbbdbaao&           amQ]>>>>>>>>>>i>><><><xQZ                                                                                      
              dmZZZZZmq                      oqwmZZmZmp                 kqZmZx(((((((xZmZqa           WakddbbbbbbbbbdbbbbboW        wY-<>>>>>>>>>>>>>>>>><><>f00                                                                                    
         qmZO0||||(|||zZZmp              awZOv(((||||/Ywmw            bmZj1)||((((|(|((((t0wa       &*abkbmJYYUmdbddddpQUUYU*&     Y?<<>>i>>>i>>>>>>>>>><><<>[xu                                                                                    
       ZZ0|||///|||(||||//nOq          hOr/|//((|||||(|(||cwd       kZQt)((}?-?{|)))((({---[CZk    %adddwJt^^^IjYmdbdCX{*^^>cQ   hmJ_<>>>>i>>>>>>>>><>><<|rrru                                                                                      
     wZC||||[[_?||||||||{???(Ow      aZf/||1--?}((((|(|({?_?nmh     0f|(([];```l?1(|({-<^`**~[Y    %adddc,`^,><~?Ldbd),^^Ii>>(M  U+>>>>>>>>>i>>>>><>>_{}{|                                                                                          
     t|||(]-^``^+](|||1]<^``,_{m    of|/|)_i`*`*+]|((([+I``^!?X     kt((1l`*^l~~~])((-^``*>~_-X   M*kdddz*``iaW&Mbddb)*``?MW&&#M U_>>><>>>>>>>>><}{}f  LL00O            00Q0m           QQOZZd           U0OOOq           ZOOOOm           0Q000    
     Q|(|1^```~++-)(|(~^``,<?_]Z    of/||~``**__+?(|((<`^*!_++v   hOC/((1I``^YW&&0(()?^``<a&&WmOd8hpdbddY?<^;XLkabddpx+;^>UJkhdd&U_<<>>>>>>i>>>>?ZmZZ bl**^:            :**`Z           ;*``*Y           +*``,z           +.`*>r           x`**{    
   kkL|||1*`*:M88Mj/||~```-aW&&ab  kL/||)l^`^}&&Wwt||(i``^rW&&aZo L(((((1<:``t0OQz)((}I,*!zLQLf)O8adbbbbdbY]-_{Zbdbbbdpu-_-(pbbb8U_>>>>>>>>>>i>>>>>>+CL!;i<<            _<i<~           -<!!~Q           [<><+0           /~<~1Y           ui>if    
  *X(||||)lI`*zCmdf|||+I,^iY0wqtfhot/|(||{~;`-LC0Xt((|[<^^1QQ0X|z Q|(((((()<:;l[(((|((({I;:l{)()O%hdbbbbbbbddbdbdbdbdbbbbbbbbbbk8k)]+>i>i>i>>>>>>>>>>><<~n0OZm                                                                                      
  %X((|||||(I;;l)||/|/||]III<1|/fho/|||/|||{~++-)|(|||(|]~~+[|||X Q|(|(((((|(((((|((((()((((((()08hdbbbbbddbdbdbbbbbbbbbbbbbbbbb8  J]i>>>>>i>>>>i>>>>>>>>>>>>fOO                                                                                    
  %X(|||(|(||||||||||||///||((||faot|||||||||||||(|||||((|||||||Y Q|((|(|((((((|(|(((((((|(((|((0%hdbddhbbbdbbdppqpdbbbbbpdpdbbb8  mf]~<>>>>>i>i>>>>>>>>>>>i<+?[                                                                                    
  %X|(||||||||||||/|//||||||||||faat|||/||||||||(||||||/|/||||||X Q/((/vn(()(|(xXXXn((|((|nu/(()0%addpo #pppddkW  hkdbbdph8Mbdbb&    wf-_>>>>>>>>i>>i>>>ii>+?{                                                                                      
  %Y|||/vc//||||rXYUf|||||tcu||/taat|||tft|||||/tttt/|||||fft|||Y Q|tzYdmJr())1L   L|(|/zcqLUrt(0 opo     #bddb#  Mkpdpa&    Mpb       Zv[[[?>>i>ii>>>>?}}{u                                                                                        
  %X|tzC&oYz/||tW  #r|||/cQomXc/fhot(jxb8Lj/||/xL  &z((|tjp8Z/||z Q/Jp     0f/tq   Ottfzm    LYnZ                                           w1}{}{}}}[)|                                                                                            
   vfj     &vucz    Cvxx0k    znxoWXc8    MQfjfYp  qJrtrp    %m/0 """,                                                                                                                                                                              
    """                                                                                                                                                                                                                                             
                                                                                                            &#""""""oW                      bOOO00OOO0mp                                                                                            
                                                                             bZZmmZZOw                   ##*obbbbbbbdbaao&              Z0OOx~<>><>>><-JZZZm                                                                                        
                                             oqmZZZZZq                  kqmmZn(((((((xZmZqa           W*adbdbbbbbbbbdbbbbkoW         amQ]>>>>>>>>>>>>><><><xQZ                                                                                      
              dmZZZZZmq                  awZOU|||(|||/XOZZb           bmmj))|((((((((((((tOqa       &aakbbZvnxzmdbdbddpJvuvY*&      wY-<>>>>>>>>>>>>>>>><>><>t0O                                                                                    
         qmZO0||||(|||zZZmp            hOr/|/||)(||||((|(|uwd       kZQt)((}]-?{|)))((()---[CZk    %adddZu{*^`IjYmdddJv]*^^>cQ     Y?<<>>>>i>>i>>i>>>>><><<><><?                                                                                    
       ZZ0|||///|||(||||//nOq        aZt/||(?--}|((((((|{?_?nmh     0f|((?_:`*`I_{(((1-<^`*^~[U    %adddz,``:?_~?Ldbb),^^l-~>(M  hmJ_<><>i>>>>>i>>>>>>>><>><><>)QZ                                                                                  
     wZC||||[[_?||||||||{???(Zw     of//|1_!```*+](((([+I*`^!?X     kt)(1I`*`i+--[()(-```^>~_-X   *abdddz*`^iaW&Mbddd)","?#W&&## U+>>>>>>>>>i>>>>>>>>>>>>>>>><<<i+                                                                                  
     t|||(]-^``^+](|||1]<^``,_{m    of|||_```,>ii~)||(<```!_++v   hOC/(|{I``^UW&&0)((?^``<a&&WmOp8apdbddY?>^:XQbabdddx+;^>JJkhdb&U_<>>>>>>>>>>><<<<<<>>>>>>>>>>>i-XYYJ            ZCZZO            J0OOO            ZZ0Ow            OOOO0          
     L|(|1^```~++-)(|(~^``,<?_]Z   kL/||(-^``}W&&an|((i``*YW&&aZo L((((()<,^`f0OQz(((}I,*!XLQLf)O%hdbbbbdbU?--}mbdbbddpu-_-(pbbb&U_>>>>>>>>>>>><<>>>>><>>>>>>>>>>;^`*;            ;*``<d           +*``]z           +*``r            >**`n          
   dZC/||1^``:M8&Mj/||~```-aW&&ab at|||||{<:^<JLLCf|(|[<^^1Q00X|z Q|(((((((i;;l[((((((({!;:!{(()0%hbbbbbbddbddbddbdbbbdbbbdbbbkb8U+>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>i~            _!i>{d           [iii(0           t>!>u            1>iiY          
  #X|(|(|)!I**zCmbf|||+I,^iY0wqtfha/|(||||(1~~~+)(|||(|(]+~+[|||X Q|((((((((((((((((((()((|(((((08hdbbbbbdbdbbdbbbdbbbbbbbbbbbbk8d)[+>>>>>>>><>>><>>>>>>>i>i>i>+])                                                                                  
  %X(|||||((I;;l)|/||/|(]III<1(/fho/||(||||||||||(|((|(((((|||||Y Q|((()(((()((((((((((((|((((()0%hdbbbbbbdpdbbdbbbbbpbpbbbbbbkb&  U[i>i>i>>>>>>>>>>>>>>>>>>>>>{o                                                                                   
  %X(||(|||(||||||||/||///||(|||fhof(|((|(||||||(((||||((|||||||X Q((()((((uz/()(((((tuu|(((((()0 hpddbdddh *bpbdbbddo%#bbbbbbpb8  wt]~<>>>>>i>>i>>>>>>>>i>>>_[)                                                                                    
  %X((|||(||||||||||||||((|(((||faat|||||||tu/|/|||||/xrt||||||/X dXx|((|uYk Qzr)((fcC pYu|(||nvp  8*ddpa     Wkdbd*%    #ddpk       qt-->>>>>>>>>>>>>>>>i>+[1                                                                                      
  %Y|||||||/nY//|||||/fzx|||||(|ta#cf|((|/t0@qft|((|tjm8L/|||||/0   pUnnYk     0rnvQ     QxuntZ                                        Zu}[[->>i>i>ii><?}}{u                                                                                        
   cf/|||/nz&%Yz/|||tnw8LJv/|||uYa  8Cr/rz     qcjtnp    &Otfj0                                                                             w1{}}{}}}}1|                                                                                            
     unfju      Xtcvb     ujtuJ#   """,                                                                                                                                                                                                             
    """                                                                                                                                                                                                                                             
                                                                                                            &#""""""oW                                                                                                                              
                                                                             bZZmmZZOw                   ##*obbbbbbbdbaao&                  bOOO00OOO0mp                                                                                            
                                             oqmZZZZZq                  kqmmZn(((((((xZmZqa           W*hdbdbbbbbbbbdbbbdboM            Z0OOx~<>><>>><-JZZZm                                                                                        
              wZZZZZZmw                  dmZOU|||(|||/XOOZ            bmmj))|((()((((((((tOqa       &oabbbmYccUmddbdddpQXzvYoW       amQ]>>>>>>>>>>>>><><><xQZ                                                                                      
         qwZZ0/|||(|(|XZZmp            oZn/||/((((|||((|||uwd       kZQt)((}]-?{|)))((()---[CZk    %adddmv1^^`;jYmdbdJv-^`^!fzM     wY-<>>>>>>>>>>>>>>>>><><>f00                                                                                    
       qm0|||/|/|/||||||/|xOw        oZj//|(?--}((((((|({?-?nmh     0f|((?_,^``l?{)((1-<``**~[Y    %adddz,``:?-~?Ldbb),^^l?]]x     Y?<<>>i>>i>i>>>>>>>>><><<>[xu                                                                                    
     wZC||||}[]{|||(||||}?-?(Ow      n//|)_>^`*,+]|((([+I*`^!?X     kt)(1I`*`l<~~])((-^``*>~+-Y   M*kdbbX*``iaW&Mbddd)","]#W&&*M hZJ_<>>>>i>>>>>>>>>>>>><|rrru                                                                                      
     t|(|([?^``*_?(|||}?!^``,_{m     X|||+```,+_+[||((<``*!_++v   hOC/(|{I``^UW&&0(((?^``<h&8WmOp8apbbbbU]<^:XLkabdddr_;^>JJkhbdWU+<><>>>>>>>>>>>><><-){{|                                                                                          
     /|||1*``^<++-((|(<``^,<_~-0   hQt||(l^``}&&Wau/((i``^j&&&aZo L((((()~:^`t0OQz)(({i;`!XLQCf)O%hdbbdbbdU?--{Zbdbbddpu-_-(dbbb&U_<>>>>>>>>>>>><}{}t      LLQQO            ZQZZZ            0OOOO           ZZZOOq           O0OOLO           w00Q0
   kbC|||1^`*:M88Mj|||~```-aW&&ab ot|||||{~:`~LCQCj(|([>*^|L0QX|z Q|(((((((>;Il[((|(((({iIIi{(()0%hbbbbbbddbbddbddbdbbddbbbbbbbb8U_>>>>>>>>>>>i<?OmmZ     h-`*^:            :``^t            :```x           -I``,Y           +,*`*x           j*``+
  *X|||||)lI`*zCmdf|||+I,^iYQOwtfhat|(/|||(}~++_)(||||(|]~~+[|||X Q|((((((((((((((((((()|(((((((08hdbbbbbbdbdbbdbbbbbbbbbbbbbbbb8U+>>>>>>>>>i>>>>>>>~JOZZC +<>>-            _!i~v            _<iiJ           f}i!>L           f-~~_X           u<ii}
  %X(||((||(l;;l)|/|/|||]III<1|/fhot(|||||||||||||(||||(|(|||||/X Q|(()()((((((|||((((((((|(((()0%hdbdbbdbddbbdppppdbbbbbbbdbbbk8b1[+>>>>>i>>>>>>>>>>>><<uOZZm                                                                                      
  %X(|||||(|(||||||||/||/||((((|fhat|(||||(|||(|(((|(|||||||||||X Q|((/vn()()|(rXXXn(((((/nv/(((0%addpo #pppddk&  hkdbbbph&Mbdbb&  J]i>>>>>>>>>>>>>>i>>>>>>>>fO0                                                                                    
  %X(||||(|||||(||//||/||/|||(||fho/|||nvf||||||xvcv/||||tru/|||Y8m//vLkp0c|)))L   L|((tLJhQJnf(0 oqo     #bddb#  Mhpdpa     Mdd   mf]~>>>>>>i>ii>>>>>>>>i>i<+][                                                                                    
  %X|||fcz//|||/rXYUf|||||tcu|//taa/|jzo%qYx|||xC  Mv((|fzb8qut|X wXQd     wvvck   pzUcCq    LYxZ                                    qt?_>>>>>>>>>>>>>>>>i>+[1                                                                                      
  %X|jUC XXz/||tW  #r||(tcQowXc/fh*vXM    8ZfuuCk  q0znrp     qnm                                                                      Zv[[[->>i>i>i>i<?}}{u                                                                                        
   cju     &UzYUW   CUvx0k    Ccv*                                                                                                          w1{}{}}}}}1| """,                                                                                       
    """                                                                                                                                                                                                                                             
                                                                                                            &#""""""oW                                                                                                                              
                                                                             bZZmmZZOw                  &ooohbbbbbbbdbooo&                                                                                                                          
                                             awwmZmZmq                  kqmmZn(((((((xZmZqa           WakddbbbbdbbbdddbddkoW                bOOO00OOO0mp                                                                                            
              dmZZZZZmq                  awZOU|(|(||||XOZZb           bmmj))|((((((((((((fOqa       &*abbbmXvnXmddbdbdpQXczJ*&          Z0OOx~<>><>>><-JZZ                                                                                          
         qmZO0||||(|||zZZmp            aOr/|//(((||||((|(|uwb       kZQt)((}]-?{|)))(()1?_-[CZk    %adddZv1*^^IjYmdbpLX}^`^>cQ       amQ]>>>>>>>>>>>>>>>~_                                                                                          
       ZZ0|||//|/||(||||/|xOw        hOt/||)?--}((((|(||{--?fQb     0f|((?_,```;~}((({-<``*^~[U    %adddz,`^,<><?Qdbb(,^^;!i>(      wY-<>>>>>>>>>>>i>><txn                                                                                          
     wZC||||[[]{||||||||}?-?(Ow     ot//|)_>`*`,+]|((([+I```l~z     kt)(1I`*^>][[{)((?```*>~_-X   #*kdddz*``ihW&Mbddd)*``?MWW&#M   Y?<>>>>>>>>>>>>>>+/nn                                                                                            
     t|||([?^``^+]((||}?!^``,_{m    of||(i^*`,+_+?)|((>``*!_++u   hOC/(|{I``^Y&&&0(((?^^`<h&&WmOp8apbbbbU?>^;XQbabdddr+;^>UCkhdb&aZJ_<><>>i>>>>>><>}j                                                                                               
     /|(|1*``^<++-)||(<``^:~--[O   kL/||(<^``{&&Wwt/((>``*u&&&aZo L((((()~:^^1zXXn)((1~!`!XLQLf)O%hdbbbbbdU?-_{Zbdbbddpu-_-(dbbk&Y_>><>>>>>>>i>>~|u                                                                                                 
   ddJ/||1^``,M8&Mj|||~```-hW&&bZ of|||||{<:^_0CQUt((|]<^^1L0QY|z Q||((((((~I!>}((|(((({~il~1(()0%hbbbbbdbbdbbbdbddbbbddbbdbbbbb8U_<>>>>>>>>>>+[x    LL00O            LYYU            CJCCL            JJJJQw           CJJYJq           OQQQZ      
  #X|||||)lI`*zCmbf|||+I,^iY0qpjtho/|(||||(1++~_)|(||||(]+~+[|||X 0((((((((((((((((|((()((((((((08adbbdbbdbbbbdbbbbbbbbbbbbbbbkb8U+<>>>>>>>>>>}OZ   h;*`^;            :""'b           I^``:b           _^.`ic           ~```{U           f``^t      
  %z(|(|(||(l;;l)||//|||]I;;<1(/fhof|||||||||||||||||||(|(||||||X Q|(()(((((()((|(|((((((|((((()0%hdbbbbbbdpbbbddbbbbpbdbbkbbbbb8U+>>>>>>>i>>i>>-QZ  _<>>~            _ii~            ?-+<_            }!li]L           f~~<|J           x>>ix      
  %X(|||(|((||||||||||/|/|||((||fao/|||||||||||||((||||((|||||||X Q((|(((((nct(((((((tuu|(((((|)0%hdpbbbddh *bpbdbbdda%hddbbbbdk p1[~>>>>>>>i>>>>><CO                                                                                               
  %X((|(||||||||(||||||||||(((||fhot|||||||fjt|||(|||/rft|||/||/X dUn|(((xzb ZYr|()fXZ OYu/(||vXd   Mbdqo     Mddddo%    #ddpb     U[i>>>i>i>>>>i>>>+COZ                                                                                            
  %X(|||||//zX//||||//tzx|||||(/taort||||/tQBdf|(||/tjm8L/||(||/0   o0zuYk     wXccZ     dUJJcp                                    mf]~>>>>>>>i>>ii>>+~zLL                                                                                          
   JYn|||tYU8%Yz/|||tXY UJv/||(vXa  &Ur/nL     wnf/np     pxttZ                                                                      wf-->>>>>>>>>>>>>>>~c                                                                                          
     pYzXJ      YJUYh     CYYJJM                                                                                                       Zu}[[?>>iii>i>>>-}1                                                                                          
                                                                                                                                            w1}{}{}}}[)|  """                                                                                       
    ]   

    # Combine ASCII art with formatted text
    help_text = f"{ascii_animation[0]}\n\n{readme_content}"

    # Create a new window for help
    layout = [
        [sg.Text('', font=('Courier New', 8), size=(244, 26), justification='center', key='-ASCII_ANIMATION-')],
        [sg.Text(readme_content, font=('Courier New', 16), size=(160, 60), justification='left', key='-HELP_TEXT-')],
        [sg.Button('Close')]
    ]

    help_window = sg.Window('Help', layout, finalize=True)

    # Animation loop
    frame_index = 0
    while True:
        event, _ = help_window.read(timeout=500)  # Adjust the timeout to control animation speed

        if event == sg.WIN_CLOSED or event == 'Close':
            break

        # Update the ASCII animation frame
        frame_index = (frame_index + 1) % len(ascii_animation)
        help_window['-ASCII_ANIMATION-'].update(ascii_animation[frame_index])

    help_window.close()

def game_main():
    layout = [
        [sg.Text("Main Window")],
        [sg.Button('Open Game 1'), sg.Button('Open Game 2'), sg.Button('Open Game 3'), sg.Button('Open Game 4'),sg.Button('Exit')]
    ]

    window = sg.Window("Main Window", layout)

    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == 'Exit':
            break
        elif event == 'Open Game 1':
            game_window = create_game_window('NGMI panda')
            while True:
                game_event, game_values = game_window.read()
                if game_event == sg.WIN_CLOSED or game_event == 'Close':
                    break
                elif game_event == 'Play':
                    game_1()
                    sg.popup("You're playing Game 1!")
            game_window.close()
        elif event == 'Open Game 2':
            game_window = create_game_window('Definitely not Oregon Trail')
            while True:
                game_event, game_values = game_window.read()
                if game_event == sg.WIN_CLOSED or game_event == 'Close':
                    break
                elif game_event == 'Play':
                    game_2()
                    sg.popup("You're playing Game 2!")
            game_window.close()
        elif event == 'Open Game 3':
            game_window = create_game_window('I cant remember')
            while True:
                game_event, game_values = game_window.read()
                if game_event == sg.WIN_CLOSED or game_event == 'Close':
                    break
                elif game_event == 'Play':
                    game_3()
                    sg.popup("You're playing Game 3!")
            game_window.close()
        elif event == 'Open Game 4':
            game_window = create_game_window('Ghosts AI')
            while True:
                game_event, game_values = game_window.read()
                if game_event == sg.WIN_CLOSED or game_event == 'Close':
                    break
                elif game_event == 'Play':
                    game_4()
                    sg.popup("You're playing Game 4!")
            game_window.close()

def create_gui():
    # Define the layout for the main content area
    main_layout = [
        [sg.Text("1. "), sg.Button("Open The Codex.", key='-CODEX-')],
        [sg.Text("2. Search SEC archives for search term:"), sg.InputText(key='-SEARCH-', size=(10, 1)), sg.Button("Search"), sg.Text(" ", size=(3, 1)), sg.Text("or, Enter CIK to scrape: "),
         sg.InputText(key='-CIKINPUT-', size=(10, 1)), sg.Button("Scrape")],
        [sg.Text('3. Select a CSV file or navigate through /edgar/data/:')],
        [sg.Text("Current Directory:", key='-CURRENT_DIR_LABEL-'), sg.Input(key='-CURRENT_DIR-', readonly=True, size=(50, 1))],
        [sg.Listbox(values=[], size=(30, 15), key='-FILE_LIST-', enable_events=True),
         sg.Listbox(values=[], size=(60, 15), key='-FILES_LIST-', enable_events=True)],
        [sg.Text("Selected CSV file:"), sg.InputText(key='-CSV-', readonly=True), sg.Button('Open CSV', key='-OPENCSV-', visible=False)],
        [sg.Button('Back'), 
         sg.Button('Search company filings for a keyword', key='-PARSE_GUI-', visible=False, disabled=True),  
         sg.Button('View File', key='-VIEW_FILE-', visible=False),  
         sg.Button('Download CSV', key='-DOWNLOAD-CSV-', visible=False),
         sg.Button('Download Crawl', key='-DOWNLOAD-CRAWL-', visible=False)],
        [sg.Button("Play games?", key='-PROCEED-')],
    ]

    # Define the layout for the second column from right (for search and file operations)
    search_column = []

    # Define the layout for the rightmost column (for process and exit)
    action_column = [
        [sg.Text('', size=(1, 15)), sg.Text('', key='-ANIMATION-', size=(22, 12), justification='center')],
        [sg.Button("HELP", key='-HELP-', button_color=('white', 'red'), size=(6, 2)), sg.Text('', size=(15, 1)), sg.Button("Exit", key='-EXIT-', size=(6, 2))],
    ]

    # Combine layouts into the final window layout
    layout = [
        [sg.Column(main_layout, vertical_alignment='top', key='-MAIN-'),
         sg.Column(search_column, vertical_alignment='top', key='-SEARCH-'),
         sg.Column(action_column, vertical_alignment='top', key='-ACTION-')]
    ]

    return sg.Window("Script GUI", layout, finalize=True)

def main():
    from concurrent.futures import ThreadPoolExecutor
    import io

    window = create_gui()
    current_dir = os.getcwd()
    replacements_csv = "edgar_CIK2.csv"
    selected_item = None  # Initialize selected_item to None

    def remove_html_xml_tags(text):
        """Remove HTML and XML tags from the text."""
        soup = BeautifulSoup(text, 'html.parser')
        return soup.get_text()

    def clean_text(text):
        """Remove empty lines from the text."""
        return '\n'.join(line.strip() for line in text.split('\n') if line.strip())

    # Initial update of the file list
    window['-CURRENT_DIR-'].update(current_dir)
    window['-FILE_LIST-'].update(gui_directories(current_dir, replacements_csv))
    window['-FILES_LIST-'].update(list_files_in_gui(current_dir))
    start_animation(window, frames, '-ANIMATION-')
    script_dir = os.path.dirname(os.path.abspath(__file__))

    while True: 
        event, values = window.read(timeout=100)

        if event == sg.WIN_CLOSED or event == "Exit":
            break
        elif event == 'Search':
            search_term = values['-SEARCH-']
            directory = './sec_archives'  # Assuming you have a directory input somewhere
            if search_term and directory:
                print(f"Searching for '{search_term}' in {directory}...")
                #search_master_archives(search_term, directory)
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(search_master_archives, search_term, directory)
                    result = future.result()
                print("Search complete.")
            else:
                print("Please enter a search term and directory.")
        elif event == '-OPENCSV-':
            csv_file = values['-CSV-']
            if csv_file:
                TableSimulation(csv_file)  # Pass the CSV file path to TableSimulation
            else:
                print("Please select a CSV file first.")
        elif event == '-SORTEDFILES-':
            # Call your clean function here
            clean()
            with ThreadPoolExecutor() as executor:
                future = executor.submit(clean)
                result = future.result()
        elif event == '-CODEX-':
            # Call your clean function here
            codex()
        elif event == '-PARSE_GUI-':
            search_term = sg.popup_get_text("Enter search term:", title="Search Term")
            if search_term:
                window.perform_long_operation(lambda: parse_gui(search_term, current_dir), '-PARSE_COMPLETE-')
        elif event == '-UPDATE_ANIMATION-':
            key, frame = values[event]
            window[key].update(frame)
            window.refresh()
        elif event == '-PARSE_COMPLETE':
            # Assuming parse_gui returns something meaningful or you want to notify completion
            sg.popup(f"Search completed. Results saved.", title="Search Complete")
        elif event == '-HELP-':
            show_help()
        elif event == '-FILE_LIST-':  # Handle directory selection
            try:
                selected = values['-FILE_LIST-'][0]
                if selected_item == selected:
                    # Double-click action
                    path = os.path.join(current_dir, selected)
                    if os.path.isdir(path):
                        current_dir = path
                        # Update the current directory label
                        window['-CURRENT_DIR-'].update(current_dir)
                        window['-FILE_LIST-'].update(gui_directories(current_dir, replacements_csv))
                        window['-FILES_LIST-'].update(list_files_in_gui(current_dir))
                        # Reset button colors to grey for directories
                        window['-VIEW_FILE-'].update(visible=False)
                        window['-DOWNLOAD-CSV-'].update(visible=False)
                        window['-DOWNLOAD-CRAWL-'].update(visible=False)
                        # Check if we're in a subdirectory of edgar
                        if current_dir.startswith(os.path.join(os.getcwd(), 'edgar')):
                            window['-PARSE_GUI-'].update(visible=True)
                        else:
                            window['-PARSE_GUI-'].update(visible=False)
                        # Enable the button if files_list has been populated
                        if window['-FILES_LIST-'].get_list_values():
                            window['-PARSE_GUI-'].update(disabled=False)
                        else:
                            window['-PARSE_GUI-'].update(disabled=True)
                    elif os.path.isfile(path):
                        if selected.endswith('.csv'):
                            window['-CSV-'].update(path)
                            window.write_event_value('-OPENCSV-', '-OPENCSV-')
                            # Enable buttons for CSV files
                            window['-VIEW_FILE-'].update(visible=True)
                            window['-DOWNLOAD-CSV-'].update(visible=True)
                            window['-DOWNLOAD-CRAWL-'].update(visible=True)
                        elif selected.endswith('.txt'):
                            # Enable 'View File' for text files
                            window['-VIEW_FILE-'].update(visible=True)
                            window['-DOWNLOAD-CSV-'].update(visible=False)
                            window['-DOWNLOAD-CRAWL-'].update(visible=False)
                        else:
                            # Disable all buttons for other file types
                            window['-VIEW_FILE-'].update(visible=False)
                            window['-DOWNLOAD-CSV-'].update(visible=False)
                            window['-DOWNLOAD-CRAWL-'].update(visible=False)
                else:
                    # Single-click, just highlight
                    selected_item = selected
            except Exception as e:
                print(f"Error processing selection: {e}")
                selected_item = None
        elif event == '-FILES_LIST-':  # Handle file selection
            try:
                selected = values['-FILES_LIST-'][0]  # Ensure selected is always defined
                if selected_item == selected:
                    # Double-click action
                    path = os.path.join(current_dir, selected)
                    if os.path.isfile(path):
                        if selected.endswith('.csv'):
                            window['-CSV-'].update(path)
                            window.write_event_value('-OPENCSV-', '-OPENCSV-')
                            # Enable buttons for CSV files
                            window['-VIEW_FILE-'].update(visible=True)
                            window['-DOWNLOAD-CSV-'].update(visible=True)
                            window['-DOWNLOAD-CRAWL-'].update(visible=True)
                        elif selected.endswith('.txt'):
                            # Display text file content
                            with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                                content = file.read()
                                cleaned_content = clean_text(remove_html_xml_tags(content))
                                sg.popup_scrolled(cleaned_content, title=f"Content of {selected}", size=(80, 30))
                        else:
                            # Disable all buttons for other file types
                            window['-VIEW_FILE-'].update(visible=False)
                            window['-DOWNLOAD-CSV-'].update(visible=False)
                            window['-DOWNLOAD-CRAWL-'].update(visible=False)
                else:
                    # Single-click, just highlight
                    selected_item = selected        
            except Exception as e:
                print(f"Error processing file selection: {e}")
        elif event == '-VIEW-FILE-':  # Handle viewing the selected file
            try:
                selected_file = values['-FILES_LIST-'][0]
                if selected_file:
                    file_path = os.path.join(current_dir, selected_file)
                    if file_path.endswith('.txt'):
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                            content = file.read()
                            cleaned_content = clean_text(remove_html_xml_tags(content))
                            sg.popup_scrolled(cleaned_content, title=f"Content of {selected_file}", size=(80, 30))
                    elif file_path.endswith('.csv'):
                        window['-CSV-'].update(file_path)
                        window.write_event_value('-OPENCSV-', '-OPENCSV-')
                    else:
                        sg.popup(f"File selected: {selected_file}")
            except Exception as e:
                print(f"Error viewing file: {e}")
        elif event == 'Back':
            parent_dir = os.path.dirname(current_dir)
            if parent_dir != current_dir:
                current_dir = parent_dir
                window['-CURRENT_DIR-'].update(current_dir)
                window['-FILE_LIST-'].update(gui_directories(current_dir, replacements_csv))
                window['-FILES_LIST-'].update(list_files_in_gui(current_dir))
                # Check if we're in /edgar/data for button visibility
                if current_dir.endswith('edgar'):
                    window['-PARSE_GUI-'].update(visible=True)
                else:
                    window['-PARSE_GUI-'].update(visible=False)
                    try:
                        parent_dir = os.path.dirname(current_dir)
                        if parent_dir and parent_dir != current_dir and parent_dir != script_dir:
                            current_dir = parent_dir
                            window['-CURRENT_DIR-'].update(current_dir)
                            # Update both directory and file lists
                            window['-FILE_LIST-'].update(gui_directories(current_dir, replacements_csv))
                            window['-FILES_LIST-'].update(list_files_in_gui(current_dir))  # Repopulate files list
            
                            # Check for CSV and TXT files in the current directory, excluding the hidden ones
                            has_files = any(file.endswith(('.csv', '.txt')) and (not file.endswith('.csv') or file not in {'edgar_CIKs.csv', 'edgar_CIK2.csv'}) for file in os.listdir(current_dir))
            
                            # Adjust button visibility based on directory content
                            if has_files:
                                window['-OPENCSV-'].update(visible=True)  # Assuming this is for CSV files
                                window['-DOWNLOAD-CSV-'].update(visible=True)  # Assuming this is for CSV files
                                window['-DOWNLOAD-CRAWL-'].update(visible=True)  # Assuming this is for CSV files
                                window['-VIEW_FILE-'].update(visible=True)  # For both CSV and TXT files
                            else:
                                window['-OPENCSV-'].update(visible=False)
                                window['-DOWNLOAD-CSV-'].update(visible=False)
                                window['-DOWNLOAD-CRAWL-'].update(visible=False)
                                window['-VIEW_FILE-'].update(visible=False)
                
                            # Check if we're still in edgar or if we've moved out
                            if current_dir.startswith(os.path.join(os.getcwd(), 'edgar')):
                                window['-PARSE_GUI-'].update(visible=True)
                            else:
                                window['-PARSE_GUI-'].update(visible=False)
            
                            # Enable/disable based on files in directory
                            window['-PARSE_GUI-'].update(disabled=not window['-FILES_LIST-'].get_list_values())
            
                            # Reset button colors to grey for directories if no files are selected
                            if not window['-FILES_LIST-'].get_list_values():
                                window['-VIEW_FILE-'].update(visible=False)
                                window['-DOWNLOAD-CSV-'].update(visible=False)
                                window['-DOWNLOAD-CRAWL-'].update(visible=False)
            
                    except Exception as e:
                        print(f"Error moving back: {e}")
        elif event == 'Scrape':
            edgar_url = "https://www.sec.gov/Archives/edgar/data/"
            directory_part = values['-CIKINPUT-']
            sec_url = edgar_url + directory_part
            testing(sec_url)
        elif event == '-PROCEED-':
            game_main()
        elif event == '-DOWNLOAD-CSV-':
            csv_file = values['-CSV-']
            if csv_file:
                popup_layout = [
                    [sg.Text("Downloading from CSV stored URLs...")],
                    [sg.Multiline(size=(40, 10), key='-OUTPUT_POPUP-')]
                ]
                popup_window = sg.Window("Download Progress", popup_layout, modal=True, finalize=True)
                popup_window['-OUTPUT_POPUP-'].update("Starting download...\n")
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(download_from_csv, csv_file)
                    result = future.result()
                popup_window['-OUTPUT_POPUP-'].update("Download complete.\n")
                popup_window.read(timeout=1000)  # Wait for 1 second to show the message
                popup_window.close()
            else:
                print("Please select a CSV file.\n")
        elif event == '-DOWNLOAD-CRAWL-':
            csv_file = values['-CSV-']
            if csv_file:
                popup_layout = [
                    [sg.Text("Downloading from crawling Edgar system...")],
                    [sg.Multiline(size=(40, 10), key='-OUTPUT_POPUP-')]
                ]
                popup_window = sg.Window("Download Progress", popup_layout, modal=True, finalize=True)
                popup_window['-OUTPUT_POPUP-'].update("Starting download...\n")
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(download_from_crawling, csv_file)
                    result = future.result()
                popup_window['-OUTPUT_POPUP-'].update("Download complete.\n")
                popup_window.read(timeout=1000)  # Wait for 1 second to show the message
                popup_window.close()
            else:
                print("Please select a CSV file.\n")
        elif event == '-EXIT-':
            break

        # Enable/disable the Process button based on whether a file is selected
        window['-OPENCSV-'].update(disabled=values['-CSV-'] == '')
        window['-DOWNLOAD-CSV-'].update(disabled=values['-CSV-'] == '')
        window['-DOWNLOAD-CRAWL-'].update(disabled=values['-CSV-'] == '')

    window.close()

if __name__ == '__main__':
    try:
        # Get the current working directory directly
        current_directory = Path.cwd()
        
        # Define your download directory relative to the script's execution directory
        download_directory = current_directory / 'sec_archives'
        
        # Ensure the directory exists
        download_directory.mkdir(parents=True, exist_ok=True)

        #print("Normalized Path:", normalized_path)
        print("checking and importing any missing modules")
        check_and_install_modules()
        import_modules()
        # print("downloading archives to /sec_archives/ ")
        # download_pre_files()
        # download_daily_index_files()  # This will handle the daily files for Q3 2024
            
        # Loop through each URL with an index for naming
        for index, url in enumerate(urls):
            # Use the predefined filenames
            output_path = "./" + file_names[index]

            # Attempt to download with a random User-Agent
            headers = {'User-Agent': "FORTHELULZ@anonyops.com"}
            try:
                # Create a request object
                req = urllib.request.Request(url, headers=headers)
        
                # Open the URL
                with urllib.request.urlopen(req) as response:
                    # Check if the request was successful
                    if response.getcode() == 200:
                        # Write the content to the output file
                        with open(output_path, "wb") as file:  # Use 'wb' for binary files
                            file.write(response.read())
                        print(f"File from {url} downloaded and saved as {output_path}")
                    elif response.getcode() == 403:
                        print(f"Access denied for {url}, trying fallback User-Agent.")
                        # Try with fallback User-Agent
                        fallback_headers = {'User-Agent': "anonymous/FORTHELULZ@anonyops.com"}
                        fallback_req = urllib.request.Request(url, headers=fallback_headers)
                        with urllib.request.urlopen(fallback_req) as fallback_response:
                            if fallback_response.getcode() == 200:
                                with open(output_path, "wb") as file:
                                    file.write(fallback_response.read())
                                print(f"File from {url} downloaded with fallback and saved as {output_path}")
                    else:
                        print(f"Failed to download file from {url}. Status code: {response.getcode()}")
    
            except urllib.error.HTTPError as e:
                print(f"HTTP Error occurred for {url}: {e.code} - {e.reason}")
            except urllib.error.URLError as e:
                print(f"URL Error occurred for {url}: {e.reason}")
            except IOError as e:
                print(f"IO Error occurred while writing to {output_path}: {e}")

        print("downloading archives to /sec_archives/ ")
        download_pre_files()
        download_daily_index_files()  # This will handle the daily files for 2024

        GUI_Variable = input("Graphical User Interface? hmm? (y/n):").strip().lower() or 'y'
        if GUI_Variable == 'y':
            #display_power()
            main()
        else:
            display_power()
            intro()# begin the show
            game = input("Would you like to play the game? (y/n): ").strip().lower() or 'y'
            if game == "y":
                game_2()  # Run game

            try:
                if not check_free_space():
                    print("Not enough free space to proceed. Exiting.")
                    sys.exit(1)
                edgar_CIKs() # Ensure the edgar_CIKs.txt file is created.
                if not failed_downloads:
                    print("All files downloaded successfully and present.")

                while True:
                    directory_part = input(
                        "Please enter the CIK number of the Edgar directory to be scraped, or one of the following options:\n"
                        "0. The Codex - This shows the player all the levels and things. \n"
                        "1. archives - search tool to find and list any companies SEC filings. Can also search for Last Names.\n"
                        "2. csv - function to select and process a CSV created from searching the Edgar archives.\n"
                        "3. view-files - To perform an Edgar inventory check.\n"
                        "4. parse-files - To parse SEC filings after processing.\n"
                        "5. help - To get information about all the things.\n"
                        "69. AllYourBaseAreBelongToUs - An absolutely horrible option that fills up your ENTIRE harddrive with SEC filings.<< (hint: srsly NOT advised.)\n"
                        "0. Return to main menu.\n"
                        "Enter your choice: ").strip()

                    if directory_part == "0" or directory_part == "Codex":
                        print("Easter egg found. This allows you to know what to search for.")
                        codex()
                    elif directory_part == "1" or directory_part == "archives":
                        print("You have chosen to search the master archives and output a CSV of results for view-files and parse-files to use.")
                        verify_and_prompt()
                    elif directory_part == "2" or directory_part == "csv":
                        csv_files = list_csv_files("./")
                        if not csv_files:
                            print("No CSV files found.")
                            continue

                        print("Available CSV files (without '_results.csv'):")
                        for i, file in enumerate(csv_files):
                            print(f"{i + 1}: {file[:-len('_results.csv')]}")

                        file_choice = int(input("Select a CSV file by number or enter 0 to exit: "))
                        if file_choice == 0:
                            continue

                        if 1 <= file_choice <= len(csv_files):
                            csv_file = csv_files[file_choice - 1]
                            print(f"Selected CSV file: {csv_file}")
                            CSV_EXTRACTION_METHOD = input("use archves URL listings or crawl SEC site? (options are 'url' or 'crawl')").strip()
                            if CSV_EXTRACTION_METHOD == 'url':
                                # function to read URLs from CSV and download them directly from created list.
                                download_from_csv(csv_file)
                            elif CSV_EXTRACTION_METHOD == 'crawl':
                                # function to use the CIK's to crawl and download in a more aggressive way.
                                download_from_crawling(csv_file)
                            elif directory_part == "0":
                                continue
                            else:
                                print("please enter url, crawl, or 0 to go back to main menu")
                            print("Processing of CSV URLs complete.")
                        else:
                            print("Invalid choice.")
                    elif directory_part == "3" or directory_part == "view-files":
                        print("Beginning downloaded Edgar filings check.")
                        clean()
                    elif directory_part == "4" or directory_part == "parse-files":
                        print("Proceeding with parse option.")
                        parse(sec_urls=None)
                    elif directory_part == "5" or directory_part == "help":
                        print("\nIn the structure http://www.sec.gov/Archives/edgar/1157644/, the numbered subdirectory represents an accession number, which is a unique identifier assigned automatically to an accepted submission by the EDGAR (Electronic Data Gathering, Analysis, and Retrieval) system. Accession numbers are used to identify and retrieve filings made by companies with the Securities and Exchange Commission (SEC).\n")
                        print("An accession number typically consists of a combination of digits and dashes, such as 0001193125-15-118890. This specific format is used to distinguish accession numbers from other types of identifiers, like Central Index Key (CIK) numbers or company names.\n")
                    elif directory_part == "69" or directory_part == "AllYourBaseAreBelongToUs":
                        print("Easter egg found. This allows you to download ALL SEC filings.")
                        sec_processing_pipeline()
                    elif directory_part == "0":
                        continue
                    elif len(directory_part) > 5 and directory_part.isdigit():
                        sec_url = edgar_url + directory_part
                        testing(sec_url)
                    else:
                        print("Invalid input. Please try again.")
            except KeyboardInterrupt:
                print("\nInterrupted by user.")
            finally:
                print("Script execution finished.")
    except KeyboardInterrupt:
        #display_power()
        print("\nInterrupted by user.")
    finally:
        print("Script execution finished.")
