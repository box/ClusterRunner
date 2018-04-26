case "$1" in
  1)  # On initial install ...
    # Add runlevel symlinks for service.
    chkconfig --add clusterrunner-master
    chkconfig --add clusterrunner-slave
  ;;
  2)  # On upgrade ...
    # Delete/add runlevel symlinks for service.
    chkconfig --del clusterrunner-master
    chkconfig --add clusterrunner-master

    chkconfig --del clusterrunner-slave
    chkconfig --add clusterrunner-slave
  ;;
esac
exit 0
