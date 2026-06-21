import re

with open('_scripts/ipo/ipo_play_selector.py', encoding='utf-8') as f:
    content = f.read()

old = """    qib      = n(ipo.get('qib_subscription_x'))
    nii      = n(ipo.get('nii_subscription_x'))
    ret_open = n(ipo.get('return_listing_open'))"""

new = """    qib          = n(ipo.get('qib_subscription_x'))
    nii          = n(ipo.get('nii_subscription_x'))
    ret_open     = n(ipo.get('return_listing_open'))
    listing_open = n(ipo.get('listing_open'))
    issue_price  = n(ipo.get('issue_price'))"""

if old in content:
    content = content.replace(old, new)
    with open('_scripts/ipo/ipo_play_selector.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("PATCHED: listing_open and issue_price added to select_play")
elif 'listing_open = n(ipo.get' in content:
    print("ALREADY FIXED: listing_open already defined")
else:
    print("ERROR: could not find patch location")
