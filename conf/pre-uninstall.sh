case "$1" in
  0)  # Only on remove (not upgrade)
  # Stop any services, if running.
  service clusterrunner-manager status >/dev/null && service clusterrunner-manager stop
  service clusterrunner-worker  status >/dev/null && service clusterrunner-worker  stop
  # Delete runlevel symlinks for service.
  chkconfig --del clusterrunner-manager
  chkconfig --del clusterrunner-worker
  ;;
esac
exit 0
