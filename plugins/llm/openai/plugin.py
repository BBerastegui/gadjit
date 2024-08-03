import base64
import boto3
import json
import requests
import logging

from models import BaseGadjitLLMPlugin


class OpenAIPlugin(BaseGadjitLLMPlugin):
    def query(self, system_prompt, user_prompt):
        url = 'https://api.openai.com/v1/chat/completions'
        headers = {
            "Authorization": f"Bearer {self.config.get('secret_key')}",
            "Content-Type": "application/json",
        }

        data = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 1,
            "max_tokens": 512,
            "top_p": 1,
            "frequency_penalty": 0,
            "presence_penalty": 0,
        }

        response = requests.post(url, headers=headers, json=data)

        try:
            result = response.json()
        except JSONDecodeError as e:
            logging.exception(
                f"The following content caused the JSONDecodeError: {response.content}"
            )
            raise e

        if result.get("error"):
            raise Exception(result.get("error").get("message"))

        try:
            if result.get("choices")[0].get("finish_reason") != "stop":
                return None
        except (KeyError, TypeError) as e:
            logging.exception(
                f"OpenAI response could not be understood. The API returned the following content: {response.content}"
            )
            raise e

        else:
            content = result.get("choices")[0].get("message", {}).get("content")
            try:
                # Diagnostic use, log the base64 of the response content for later debugging
                logging.debug(base64.b64encode(content.encode("utf-8")))
            except Exception as e:
                logging.exception(f"Could not base64 the content: {content}")

            return content

    def _get_access_token(self):
        # Have we assumed our target role and saved session creds?
        if not self.ai_gateway_role_credentials or (
            datetime.now() - self.ai_gateway_role_credentials_timestamp > timedelta(minutes=5)
        ):
            logging.debug(
                f"Refreshing AWS credentials. Last cached timestamp: {self.ai_gateway_role_credentials_timestamp}"
            )
            credentials = self.__assume_role(self.config.get('ai_gateway_role_arn'))

            # Update boto3 session with assumed role credentials
            boto3_session = boto3.Session(
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )
            self.ai_gateway_role_credentials = (
                boto3_session.get_credentials().get_frozen_credentials()
            )
            self.ai_gateway_role_credentials_timestamp = datetime.now()
        else:
            logging.debug(
                f"Using cached AWS credentials. Last cached timestamp: {self.ai_gateway_role_credentials_timestamp}"
            )

        return self.ai_gateway_role_credentials

    def __assume_role(self, role_arn):
        sts_client = boto3.client("sts")
        assumed_role = sts_client.assume_role(
            RoleArn=role_arn, RoleSessionName="aigateway-session"
        )
        credentials = assumed_role["Credentials"]
        return credentials
