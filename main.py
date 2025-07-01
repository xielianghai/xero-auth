import requests
import urllib.parse
import mysql.connector
import json
import uuid

# ====== 加载配置 ======
with open('config.json', 'r') as f:
    CONFIG = json.load(f)

MYSQL_CONFIG = CONFIG['mysql']
CLIENT_ID = CONFIG['client_id']
CLIENT_SECRET = CONFIG['client_secret']
REDIRECT_URI = CONFIG['redirect_uri']

# ====== Xero OAuth 授权链接生成 ======
def generate_auth_url():
    scope = 'offline_access accounting.transactions accounting.settings accounting.contacts'
    state = str(uuid.uuid4())  # 可替换为 uuid: str(uuid.uuid4())
    query = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': scope,
        'state': state
    }
    return 'https://login.xero.com/identity/connect/authorize?' + urllib.parse.urlencode(query)

# ====== 用授权 code 换取 access_token + refresh_token ======
def exchange_code_for_token(auth_code):
    token_url = 'https://identity.xero.com/connect/token'
    data = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    response = requests.post(token_url, data=data)
    response.raise_for_status()
    return response.json()

# ====== 获取租户（Xero Organization）ID ======
def get_xero_tenant_id(access_token):
    url = 'https://api.xero.com/connections'
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    connections = response.json()
    if not connections:
        raise Exception('No tenant connections found.')
    return connections[0]['tenantId']

# ====== 测试 Token 是否能获取 BankTransactions ======
def test_bank_transactions(access_token, tenant_id):
    url = 'https://api.xero.com/api.xro/2.0/BankTransactions'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'xero-tenant-id': tenant_id,
        'Accept': 'application/json'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        count = len(data.get('BankTransactions', []))
        print(f"✅ Token 验证成功，获取到 {count} 条 BankTransactions 数据。 {data.get('BankTransactions', [])}")
    else:
        print(f"⚠️ Token 验证失败，状态码: {response.status_code}")
        print(response.text)

# ====== 保存凭证到数据库 ======
def save_credentials_to_db(customer_id, credentials):
    conn = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = conn.cursor()
    api_credentials_json = json.dumps(credentials)
    cursor.execute("""
        UPDATE customer_accounting_settings
        SET api_credentials = %s
        WHERE customer_id = %s
    """, (api_credentials_json, customer_id))
    conn.commit()
    cursor.close()
    conn.close()

# ====== 主流程 ======
def main():
    print("🔗 Step 1: 打开以下授权链接，在浏览器中登录 Xero 并授权：\n")
    print(generate_auth_url())
    print("\n➡️ 授权完成后 Xero 会跳转到一个地址，例如：")
    print("http://localhost:8000/callback?code=xxx&state=clitool001")

    full_url = input("\n✂️ 请粘贴完整回调 URL 到这里：\n> ").strip()
    parsed = urllib.parse.urlparse(full_url)
    code = urllib.parse.parse_qs(parsed.query).get('code', [None])[0]

    if not code:
        print("❌ 未检测到 code 参数，请确认 URL 是否正确。")
        return

    print("🔄 Step 2: 正在换取 access_token 和 refresh_token ...")
    token_data = exchange_code_for_token(code)
    access_token = token_data['access_token']
    refresh_token = token_data['refresh_token']

    print("🔍 Step 3: 正在获取 XERO 租户 ID ...")
    tenant_id = get_xero_tenant_id(access_token)

    customer_id = input("👤 Step 4: 请输入对应 customer_id（UUID）以保存凭证：\n> ").strip()
    credentials = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': refresh_token,
        #'xero_tenant_id': tenant_id
    }

    print("💾 Step 5: 正在保存凭证到数据库...")
    save_credentials_to_db(customer_id, credentials)

    print("✅ 授权成功，凭证已保存！以下是存储内容：")
    print(json.dumps(credentials, indent=2))

    # ✅ Step 6: 可选验证 token 是否有效
    try:
        print("\n🧪 Step 6: 正在验证 token 是否可用（BankTransactions）...")
        test_bank_transactions(access_token, tenant_id)
    except Exception as e:
        print(f"❌ 验证失败：{e}")

if __name__ == '__main__':
    main()
