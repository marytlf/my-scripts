docker build -t mock-saml-idp .
docker run -d \
  --name saml-idp \
  -p 5000:5000 \
  -v $(pwd)/rancher_metadata.xml:/app/metadata/rancher_metadata.xml:ro \
  mock-saml-idp:latest
