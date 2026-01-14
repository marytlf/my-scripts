sudo apt install python3.12-venv
python3 -m venv venv/bin/activate
source venv/bin/activate/bin/activate

pip install minio
HOST=$(hostname)
sed -i "s/ip-172-31-0-171/$HOST/g" create-bucket-v2.py
python create-bucket-v2.py
deactivate
