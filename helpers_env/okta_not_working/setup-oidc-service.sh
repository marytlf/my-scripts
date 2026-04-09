sudo apt update -y
sudo apt install -y python3-pip python3-venv
cd ~/helpers_env/oidc

python3 -m venv venv
source venv/bin/activate

sleep 1 

pip install flask PyJWT cryptography ldap3 requests

sleep 3

TOKEN="$(curl -fsS -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")"


PUBLIC_HOSTNAME="$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" \
  "http://169.254.169.254/latest/meta-data/public-hostname")"

echo $PUBLIC_HOSTNAME

sed -i "s/PLACEHOLDER/${PUBLIC_HOSTNAME}/g" oidc_mock_server.py

sudo cp mock-oidc.service /etc/systemd/system/mock-oidc.service
sudo systemctl enable mock-oidc
sudo systemctl start mock-oidc
