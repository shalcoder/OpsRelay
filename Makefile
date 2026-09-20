install:
	python3 -m pip install -r requirements.txt

seed:
	PYTHONPATH=api python3 scripts/seed_local.py

run:
	PYTHONPATH=api python3 api/local_server.py

test:
	PYTHONPATH=api pytest -q api/tests

train:
	python3 ml/train.py --output ml/artifacts/model.joblib

sam-build:
	sam build -t infra/template.yaml

sam-deploy:
	bash scripts/deploy.sh

sagemaker:
	bash scripts/deploy_sagemaker.sh
