kubectl get nodes \
  -o custom-columns='NAME:.metadata.name,PHASE:.status.phase,WORKER:.metadata.labels.node-role\.kubernetes\.io/worker,ETCD:.metadata.labels.node-role\.kubernetes\.io/etcd,CP:.metadata.labels.node-role\.kubernetes\.io/control-plane'
echo "-----------------------------------------------------------------------------------------------------------------------------------------------------"

