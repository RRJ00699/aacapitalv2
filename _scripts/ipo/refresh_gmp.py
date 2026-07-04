import os, sys, runpy
here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["scrape_investorgain_gmp.py", "--write-db"]
runpy.run_path(os.path.join(here, "..", "scrape_investorgain_gmp.py"), run_name="__main__")
