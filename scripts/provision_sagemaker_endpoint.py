from __future__ import annotations
import argparse, time
import boto3

p=argparse.ArgumentParser()
p.add_argument('--region',required=True);p.add_argument('--role-arn',required=True);p.add_argument('--image-uri',required=True);p.add_argument('--model-data-url',required=True);p.add_argument('--endpoint-name',required=True);p.add_argument('--memory',type=int,default=2048);p.add_argument('--max-concurrency',type=int,default=1)
a=p.parse_args()
sm=boto3.client('sagemaker',region_name=a.region)
model_name=f"{a.endpoint_name}-model"
config_name=f"{a.endpoint_name}-config"
try:
    sm.delete_endpoint(EndpointName=a.endpoint_name)
except sm.exceptions.ClientError as e:
    if 'Could not find endpoint' not in str(e): raise
for _ in range(60):
    try:
        d=sm.describe_endpoint(EndpointName=a.endpoint_name)
        if d['EndpointStatus'] in {'Deleting'}: time.sleep(5); continue
    except sm.exceptions.ClientError: break
try: sm.delete_endpoint_config(EndpointConfigName=config_name)
except sm.exceptions.ClientError: pass
try: sm.delete_model(ModelName=model_name)
except sm.exceptions.ClientError: pass
sm.create_model(ModelName=model_name,ExecutionRoleArn=a.role_arn,PrimaryContainer={'Image':a.image_uri,'ModelDataUrl':a.model_data_url})
sm.create_endpoint_config(EndpointConfigName=config_name,ProductionVariants=[{'VariantName':'AllTraffic','ModelName':model_name,'ServerlessConfig':{'MemorySizeInMB':a.memory,'MaxConcurrency':a.max_concurrency}}])
try: sm.create_endpoint(EndpointName=a.endpoint_name,EndpointConfigName=config_name)
except sm.exceptions.ClientError as e:
    if 'already exists' in str(e): sm.update_endpoint(EndpointName=a.endpoint_name,EndpointConfigName=config_name)
    else: raise
waiter=sm.get_waiter('endpoint_in_service')
waiter.wait(EndpointName=a.endpoint_name,WaiterConfig={'Delay':10,'MaxAttempts':60})
print(sm.describe_endpoint(EndpointName=a.endpoint_name)['EndpointStatus'])
