import os
import sys

# Ensure proper Tcl/Tk paths for Windows Python installations during test runs
tcl_dir = "C:/Users/alire/AppData/Local/Programs/Python/Python312/tcl/tcl8.6"
tk_dir = "C:/Users/alire/AppData/Local/Programs/Python/Python312/tcl/tk8.6"
if os.path.isdir(tcl_dir):
    os.environ["TCL_LIBRARY"] = tcl_dir
if os.path.isdir(tk_dir):
    os.environ["TK_LIBRARY"] = tk_dir
