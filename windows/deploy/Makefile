.PHONY: stop download start start_master connect_slaves check test
BASE_COMMAND := ansible-playbook deploy_clusterrunner.yml -i hosts

deploy:
		$(BASE_COMMAND)

stop:
		$(BASE_COMMAND) --tags "stop"

download:
		$(BASE_COMMAND) --tags "download"

start:
		$(BASE_COMMAND) --tags "start"

start_master:
		$(BASE_COMMAND) --tags "start_master"

connect_slaves:
		$(BASE_COMMAND) --tags "connect_slaves"

check:
		$(BASE_COMMAND) --tags "check"

#test:
#		~/.clusterrunner/dist/clusterrunner build --master-url {YOUR_MASTER_HOST}:43000 git --url https://github.com/aptxkid/ClusterRunnerDemo.git --job-name Simple
