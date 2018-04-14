case "$1" in
  1)  # On initial install ...
    # Add runlevel symlinks for service.
    chkconfig --add clusterrunner-master
  ;;
  2)  # On upgrade ...
    # Delete/add runlevel symlinks for service.
    chkconfig --del clusterrunner-master
    chkconfig --add clusterrunner-master
  ;;
esac
exit 0
