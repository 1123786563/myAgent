import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'src'))

from db_helper import DBHelper
from config_manager import ConfigManager

print("Starting manual init...")
db = DBHelper()
print("Init call finished.")
