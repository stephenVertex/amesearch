#!/usr/bin/env python3

import streamlit as st
import boto3
import pprint
from botocore.client import Config
import json
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
import datetime
import re
import os

################################################################################
## CONFIG STUFF
pp = pprint.PrettyPrinter(indent=2)
bedrock_config = Config(connect_timeout=120, read_timeout=120, retries={'max_attempts': 0})
bedrock_client = boto3.client('bedrock-runtime')
bedrock_agent_client = boto3.client("bedrock-agent-runtime",
                                    config=bedrock_config)
kbId = os.environ["AME_KB_ID"]
model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
region_id = "us-east-1"
##
################################################################################


# Title of the app
st.title('Cost Optimization Bot')

# Search bar
search_query = st.text_input("Enter your search query here:")

# Display sample queries and make them clickable to populate the search bar
sample_query_1 = "What is Banjo's advice for getting started?"
sample_query_2 = "What are the steps for EBS snapshot archiving, and why is it important for cost optimization?"
sample_query_3 = "What does Jeff Barr think about 3d printing?"
sample_query_4 = "When did stephen and rahul talk about metadata filtering for knowledge bases?"

# Checkboxes for filtering content
ame_livestream = st.checkbox('AME livestream', value=True)

min_episode_number = None
max_episode_number = None


if ame_livestream:
    # Input boxes for minimum and maximum episode numbers
    min_episode_number = st.text_input("Enter minimum episode number:", value="")
    max_episode_number = st.text_input("Enter maximum episode number:", value="")


cloudfix_blog_posts = st.checkbox('CloudFix blog posts', value=True)


st.write("Try these queries:")
st.write("1. " + sample_query_1)
st.write("2. " + sample_query_2)
st.write("3. " + sample_query_3)
st.write("4. " + sample_query_4)

## Good code here: https://github.com/aws-samples/amazon-bedrock-samples/blob/main/knowledge-bases/01-rag-concepts/2_managed-rag-kb-retrieve-generate-api.ipynb

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
                'text': input + ".  If there is a list of steps or a list of bullet points, make sure there are two NEWLINE characters before the first point."
            },
            retrieveAndGenerateConfiguration=rag_config,
            sessionId=sessionId
        )
    else:
        return bedrock_agent_client.retrieve_and_generate(
            input={
                'text': input  + ".  If there is a list of steps or a list of bullet points, make sure there are two NEWLINE characters before the first point."
            },
            retrieveAndGenerateConfiguration=rag_config
        )


def construct_vector_search_config(livestream, blog_posts, min_episode_number, max_episode_number):
    # This list will hold all the conditions for the orAll filter
    or_conditions = []

    # Add a condition for 'livestream' if the livestream flag is True
    if livestream:
        ame_conditions = [{
            "equals": {
                "key": "content_type",
                "value": "ame_full_episode"
            }
        }]
        
        # Handling minimum and maximum episode numbers
        if min_episode_number:
            ame_conditions.append({
                "greaterThanOrEquals": {
                    "key": "episode_number",
                    "value": float(min_episode_number)
                }
            })
        
        if max_episode_number:
            ame_conditions.append({
                "lessThanOrEquals": {
                    "key": "episode_number",
                    "value": float(max_episode_number)
                }
            })

        # If both min and max episode numbers are provided, wrap them with andAll
        if min_episode_number and max_episode_number:
            or_conditions.append({
                "andAll": ame_conditions
            })
        else:
            or_conditions.extend(ame_conditions)
    
    # Add a condition for 'blog_posts' if the blog_posts flag is True
    if blog_posts:
        or_conditions.append({
            "equals": {
                "key": "content_type",
                "value": "cloudfix_blogpost"
            }
        })

    # Construct the vectorSearchConfiguration
    vector_search_configuration = {
        "filter": {}
    }

    # If there are any conditions, add them under the 'orAll' key
    if or_conditions:
        vector_search_configuration['filter']['orAll'] = or_conditions

    return vector_search_configuration

################################################################################
# A function to simulate search (you'll need to replace this with actual search logic)
def perform_search(query, livestream, blog_posts):
    results = []    
    vsc = construct_vector_search_config(livestream, blog_posts, min_episode_number, max_episode_number)
    vsc['numberOfResults'] = 5
    rc = { 'vectorSearchConfiguration' : vsc }
    res = retrieveAndGenerate(query, kbId, model_id=model_id, region_id=region_id, retrieval_configuration = rc)
    return res, rc

################################################################################
def load_s3_to_json(s3_uri):
    # Parse the S3 URI to get the bucket name and the object key
    if not s3_uri.startswith('s3://'):
        raise ValueError("Invalid S3 URI")

    parts = s3_uri[5:].split('/', 1)
    bucket = parts[0]
    key = '/'.join(parts[1:])

    # Create an S3 client
    s3 = boto3.client('s3')

    try:
        # Get the object from S3
        response = s3.get_object(Bucket=bucket, Key=key)
        # Read the content of the file
        content = response['Body'].read().decode('utf-8')
        # Parse the content as JSON
        json_data = json.loads(content)
        return json_data
    except (NoCredentialsError, PartialCredentialsError):
        raise Exception("Credentials are not available for AWS S3 access.")
    except ClientError as e:
        # This will catch errors such as the bucket or key does not exist
        raise Exception("Client error!")
        
################################################################################
# Extract the s3 location of the citations
def process_citations(res):
    rref = {}
    for rr in res['citations']:
        for rf in rr['retrievedReferences']:
            if 'location' in rf.keys():
                if 's3Location' in rf['location'].keys():
                    rref[rf['location']['s3Location']['uri']] = rf['location']['s3Location']['uri'] + ".metadata.json"
    metadata = {}
    for k,v in rref.items():
        metadata[k] = load_s3_to_json(v)
    return rref, metadata


def display_episode_info(episode_data):

    # Card container
    with st.container(border=True):
        col1, col2 = st.columns([1, 3])

        # Display the episode number and the show name
        with col1:
            st.subheader(f"Episode {episode_data['ep_num']}")
            st.caption(episode_data['show_name'])

        with col2:
            # Check if guest name is provided
            guest_name = episode_data.get('guest_1_name', 'Guest details not available')
            st.text(f"Guest: {guest_name}")

            # Display scheduled date
            scheduled_date = datetime.datetime.strptime(episode_data['scheduled_date'], '%Y-%m-%d %H:%M:%S')
            st.text(f"Scheduled Date: {scheduled_date.strftime('%B %d, %Y at %H:%M')}")

            # AWS services used
            if 'aws_services' in episode_data:
                st.text(f"AWS Services: {episode_data['aws_services']}")

        # Links with icons
        st.markdown("""<hr style="height:2px;border:none;color:#333;background-color:#333;" /> """, unsafe_allow_html=True)
        st.markdown(
            f"""<a href="{episode_data['linkedin_url']}" target="_blank">
                <img src="https://img.icons8.com/fluent/48/000000/linkedin.png"/> LinkedIn</a>""",
            unsafe_allow_html=True)
        st.markdown(
            f"""<a href="{episode_data['youtube_url']}" target="_blank">
                <img src="https://img.icons8.com/color/48/000000/youtube-play.png"/> YouTube</a>""",
            unsafe_allow_html=True)
        
        # Display additional links
        # st.markdown(f"**Streamyard Link:** [Here]({episode_data['streamyard_url']})")
        st.markdown(f"**Recorded Episode (Video):** [Here]({episode_data['recorded_s3_uri']})")
        st.markdown(f"**Recorded Episode (Audio):** [Here]({episode_data['audio_url']})")
        # st.markdown(f"**ClickUp Task ID:** {episode_data['clickup_task_id']}")



def extract_first_time(text):
    # This pattern matches any sequence of numbers and dots inside square brackets
    pattern = r'\[(\d+\.\d+)\]'
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    else:
        return None


# Displaying results based on search
if search_query:
    g = st.image('gears.gif', width=400)
    search_results, rc = perform_search(search_query, ame_livestream, cloudfix_blog_posts)
    g.empty()
    st.write("Retrieval Configuration")
    st.write(rc)

    # st.write(search_results['output'])
    # display_episode_info(episode_data)
    st.markdown("## Answer:")
    st.write(search_results['output']['text'])

    st.divider()

    # st.markdown("# Citations")
    md_x, md_map = process_citations(search_results)

    st.markdown("### Citations:")

    for i, cit in enumerate(search_results['citations']):
        # st.write(result)
        ct = i + 1
        st.markdown(f"#### Citation {ct}")

        st.write(cit['generatedResponsePart']['textResponsePart']['text'])
        for rr in cit['retrievedReferences']:
            st.write(rr['content']['text'])

        rr0 = cit['retrievedReferences'][0]
        rr0_txt = rr0['content']['text']
        rr0_s3  = rr0['location']['s3Location']['uri']
        rr0_md  = md_map[rr0_s3]

        if 'youtube_url' in rr0_md['metadataAttributes']:
            yt_time = extract_first_time(rr0['content']['text'])
            if yt_time is not None:
                st.video(rr0_md['metadataAttributes']['youtube_url'], start_time = round(float(yt_time)))
            display_episode_info(rr0_md['metadataAttributes'])

        if rr0_md['metadataAttributes']['content_type'] == 'cloudfix_blogpost':
            st.info("CloudFix blog post: " + rr0_md['metadataAttributes']['x_url'], icon="🔗")
        st.divider()
        
