RANCHER_URL=$(kubectl -n cattle-system get ingress rancher -o jsonpath='{.spec.rules[0].host}')

sed_placeholder(){
   sed -i "s/PLACEHOLDER_URL/${RANCHER_URL}/g" rancher_metadata.xml app.py
}


extract_new_metadata() {
    echo "Waiting for Rancher SAML metadata to become available at ${RANCHER_URL}..."

    # Loop as long as the HTTP status code is 404
    while [ "$(curl -s -k -o /dev/null -w "%{http_code}" https://${RANCHER_URL}/v1-saml/okta/saml/metadata)" -eq 404 ]; do
        echo "Still getting 404... (Rancher is likely still initializing SAML)"
        sleep 2
    done

    # Once it's no longer 404, perform the actual download
    echo "Metadata found! Downloading..."
    curl -k "https://${RANCHER_URL}/v1-saml/okta/saml/metadata" -o rancher_metadata.xml
}


build_image(){
   docker build -t mock-saml-idp .
}


#extract_new_metadata
sed_placeholder
build_image

