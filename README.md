# applipedia_exporter
Exports information from the Palo Alto Applipedia database.

## Credit to original author
This library is forked from https://github.com/oceanxsec/applipedia_exporter . I have just converted this to use async and aiohttp which drops the script runtime from 15 minutes to < 10 seconds

## How to Use
Obtain a cookie from https://applipedia.paloaltonetworks.com/ and save it to cookie.txt.

Run the commands
```bash
git clone https://github.com/ftnt-dspille/applipedia_exporter.git
pip install -r applipedia_exporter/requirements.txt
python async_exporter.py
```

The script should take less than 10 seconds.

Expected Output
```bash
python async_exporter.py
Getting application list...
Done.

Tokenizing...
Done.

Exporting info for all applications...
100%|████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 5079/5079 [00:09<00:00, 520.30it/s]
```

Then check `applipedia_exporter/output/` for the csv file of all the apps

You can view options with the "-h" or "--help" flags.

## Disclaimer
Neither this program nor I am affiliated with Palo Alto Networks in any way. This program is provided as a simple way to compile publicly-available information from Palo Alto's Applipedia.
