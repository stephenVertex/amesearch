import boto3
import os
from botocore.client import Config

from dotenv import load_dotenv
from rich import print
load_dotenv(override=True) ## make .env take precendence over shell

# Access environment variables
aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
aws_region = os.getenv('AWS_DEFAULT_REGION')
kbId = os.getenv("AME_KB_ID")

print(f"Knwowledge Base: {kbId=}")

# Create an STS client
sts_client = boto3.client('sts')

# Get caller identity
caller_identity = sts_client.get_caller_identity()

# Print the caller identity information
print(f"Account: {caller_identity['Account']}")
print(f"User ID: {caller_identity['UserId']}")
print(f"ARN: {caller_identity['Arn']}")

# Create a boto3 client using the loaded environment variables
bedrock_client = boto3.client(
    'bedrock-runtime',
    region_name=aws_region,
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
)

bedrock_config = Config(connect_timeout=120, read_timeout=120, retries={'max_attempts': 0})

bedrock_agent_client = boto3.client("bedrock-agent-runtime",
                                    config=bedrock_config)

model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
region_id = "us-east-1"

def retrieveAndGenerate(input,
                        kbId,
                        sessionId=None,
                        model_id = "anthropic.claude-instant-v1",
                        region_id = "us-east-1",
                        retrieval_configuration = None
                        ):
    model_arn = f'arn:aws:bedrock:{region_id}::foundation-model/{model_id}'
    rag_config = {
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': kbId,
                    'modelArn': model_arn
                }
    }
    # if retrieval_configuration:
    # rag_config['knowledgeBaseConfiguration']['retrievalConfiguration'] = retrieval_configuration
    print("--------------------------------------------------------------------------------")
    print(rag_config)
    if sessionId:
        return bedrock_agent_client.retrieve_and_generate(
            input={
                'text': input
            },
            retrieveAndGenerateConfiguration=rag_config,
            sessionId=sessionId
        )
    else:
        return bedrock_agent_client.retrieve_and_generate(
            input={
                'text': input
            },
            retrieveAndGenerateConfiguration=rag_config
        )

y =retrieveAndGenerate("What is Banjo's advice for getting started as a builder?", kbId, sessionId=None, model_id=model_id, region_id=region_id)    
print(y)
