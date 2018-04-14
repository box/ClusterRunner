# Stop the service if running.
service clusterrunner-master status >/dev/null && service clusterrunner-master stop
# Delete runlevel symlinks for service.
chkconfig --del clusterrunner-master
exit 0
