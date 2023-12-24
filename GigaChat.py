# Позволяет вести диалог с GigaChat

import json
import requests
import urllib3
import uuid
import time

GIGACHAT_API_URL = 'https://gigachat.devices.sberbank.ru/api/v1/'
GIGACHAT_OAUTH_URL = 'https://ngw.devices.sberbank.ru:9443/api/v2/'
GIGACHAT_CLIENT_SECRET = 'INSERT_YOUR_CLIENT_SECRET_FROM_SberID_ACCOUNT'
GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
RESPONSE_STRIP_CHARS = '«»„““”"❝❞„⹂〝〞〟＂‹›❮❯‚‘‘‛’❛❜❟`\'., '

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class GigaChat:
    """GigaChat completion assistant"""

    def __init__(
            self,
            api_url: str = '',  # GigaChat API
            oauth_url: str = '',  # GigaChat authentication
            client_secret: str = '',  # SberID Client_Secret
            scope: str = '',  # GigaChat scope
            chars_strip: str = '',  # Chars to be removed from the edges of GigaChat responses
            system_prompt: str = '',  # Role
            model: str = 'GigaChat:latest',  # model
            temperature: float = 1.0,  # default is 0.87, [0.0..2.0]
            top_p: float = 0.47,  # default is 0.47, [0.0..1.0]
            repetition_penalty: float = 1.07,  # default 1.07, [0.0..]
            update_interval: int = 0,  # default 0, [0.0..]
            n: int = 1,  # default 1, [1..4]
            max_tokens: int = 1024,  # default 512
            is_stream: bool = False,
    ) -> None:
        self._api_ulr = api_url
        self._oauth_url = oauth_url
        self._client_secret = client_secret
        self._scope = scope
        self._chars_strip = chars_strip
        self._messages = [
            {
                'role': "system",
                'content': system_prompt,
            },
        ]
        self._model = model
        self._temperature = temperature
        self._top_p = top_p
        self._repetition_penalty = repetition_penalty
        self._update_interval = update_interval
        self._n = n
        self._max_tokens = max_tokens
        self._is_stream = is_stream
        self._access_token, self._access_token_expires = self._get_access_token()

    def _get_access_token(self) -> tuple:
        """Get access token for responses"""

        headers = {
            'Content-Type': "application/x-www-form-urlencoded",
            'Authorization': f"Basic {self._client_secret}",
            'RqUID': str(uuid.uuid4()),
        }
        data = {
            'scope': self._scope,
        }
        response = requests.post(self._oauth_url + 'oauth', headers=headers, data=data, verify=False)
        if response.status_code == 200 and response.text:
            response_data = response.json()
            return response_data.get('access_token'), response_data.get('expires_at')
        else:
            print(f"Error!!! Failed to obtain access token. Server response code: {response.status_code}")
            return None, None

    def _check_access_token(self) -> bool:
        """Check access token expires at"""

        if not self._access_token:
            self._access_token, self._access_token_expires = self._get_access_token()
            if not self._access_token:
                print(f"Error!!! Failed to obtain access token")
                return False
        return self._access_token_expires > time.time()

    def get_models(self) -> list:
        """Get available models of GigaChat"""

        # Check access token
        if not self._check_access_token():
            return []

        headers = {
            'Authorization': f"Bearer {self._access_token}",
        }
        response = requests.get(self._api_ulr + 'models', headers=headers, verify=False)
        if response.status_code == 200 and response.text:
            response_data = response.json()
            return response_data.get('data')
        else:
            print(f"Error!!! Failed to getting available models. Server response code: {response.status_code}")
            return []

    def get_answer(self, message: str, **replace_texts) -> str:
        """Get text response from GigaChat by prompt"""

        # Check access token
        if not self._check_access_token():
            return

        # Replacing all special keywords to text in message
        for replace_keyword, replace_text in replace_texts.items():
            message.replace(replace_keyword, replace_text)

        # Add user message
        self._messages.append({"role": "user", "content": message})

        headers = {
            'Content-Type': "text/event-stream" if self._is_stream else "application/json",
            'Authorization': f"Bearer {self._access_token}",
        }
        data = {
            'max_tokens': self._max_tokens,
            'model': self._model,
            'messages': self._messages,
            'n': self._n,
            'repetition_penalty': self._repetition_penalty,
            'stream': self._is_stream,
            'temperature': self._temperature,
            'top_p': self._top_p,
            'update_interval': self._update_interval,
        }
        # Get response from GigaChat
        try:
            response = requests.post(self._api_ulr + 'chat/completions', headers=headers, stream=self._is_stream, json=data, verify=False)
            response.encoding = 'utf-8'
        except Exception as e:
            yield [f"[Error!!! GigaChat something wrong: {str(e)}]"]
            return

        if response.status_code == 200 and response.text:
            if self._is_stream:
                text = ''
                for line in response.iter_lines(decode_unicode=True, delimiter='\ndata:'):
                    token = line.strip("'\n ").replace('\n', '\\n')
                    if token != '[DONE]' and token:
                        token_data = json.loads(token)
                        yield str(token_data['choices'][0]['delta']['content'])
                        text += str(token_data['choices'][0]['delta']['content'])
            else:
                response_data = response.json()
                text = response_data['choices'][0]['message']['content'].strip(self._chars_strip)
                yield text
        else:
            print(f"Error accessing GigaChat, request code: {response.status_code}")
            return

        # Remember GigaChat response
        self._messages.append({"role": "assistant", "content": text})


if __name__ == "__main__":
    giga_chat = GigaChat(
        api_url=GIGACHAT_API_URL,
        oauth_url=GIGACHAT_OAUTH_URL,
        client_secret=GIGACHAT_CLIENT_SECRET,
        scope=GIGACHAT_SCOPE,
        chars_strip=RESPONSE_STRIP_CHARS,
    )
    print(f"Доступные модели: {', '.join([model['id'] for model in giga_chat.get_models()])}\n\n")
    print("Starting dialog with GigaChat:\n")

    step = 1
    while True:
        print(f"{step:2}. You:", end="\n    ")
        question = input("What do you want to ask GigaChat: ")
        if not question:
            break

        answer = giga_chat.get_answer(question)
        print(f"{step:2}. GigaChat:", end="\n    ")
        for chunk in answer:
            print(chunk, end="")
        print()

        print('_' * 100, end='\n\n')
        step += 1
