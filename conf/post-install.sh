case "$1" in
  1)  # On initial install ...
    # Add runlevel symlinks for service.
    chkconfig --add clusterrunner-manager
    chkconfig --add clusterrunner-worker
  ;;
  2)  # On upgrade ...
    # Delete/add runlevel symlinks for service.
    chkconfig --del clusterrunner-manager
    chkconfig --add clusterrunner-manager

    chkconfig --del clusterrunner-worker
    chkconfig --add clusterrunner-worker
  ;;
esac
exit 0
