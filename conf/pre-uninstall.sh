case "$1" in
  0)  # Only on remove (not upgrade)
  # Stop any services, if running.
  service clusterrunner-master status >/dev/null && service clusterrunner-master stop
  service clusterrunner-slave  status >/dev/null && service clusterrunner-slave  stop
  # Delete runlevel symlinks for service.
  chkconfig --del clusterrunner-master
  chkconfig --del clusterrunner-slave
  ;;
esac
exit 0
