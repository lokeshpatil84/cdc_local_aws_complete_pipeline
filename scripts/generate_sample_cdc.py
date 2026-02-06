import json
import boto3
from datetime import datetime


s3 = boto3.client('s3')
BUCKET = 'cdc-pipeline-dev-data-lake'

print(f"Using S3 Bucket: {BUCKET}")
print("-" * 50)

users_data = [
    {"id": 1, "name": "John Doe", "email": "john@example.com", "created_at": 1706000000000, "updated_at": 1706000000000, "__op": "c", "__ts_ms": 1706000000000},
    {"id": 2, "name": "Jane Smith", "email": "jane@example.com", "created_at": 1706000001000, "updated_at": 1706000001000, "__op": "c", "__ts_ms": 1706000001000},
    {"id": 3, "name": "Bob Johnson", "email": "bob@company.com", "created_at": 1706000002000, "updated_at": 1706000002000, "__op": "c", "__ts_ms": 1706000002000},
    {"id": 4, "name": "Alice Williams", "email": "alice@test.com", "created_at": 1706000003000, "updated_at": 1706000003000, "__op": "c", "__ts_ms": 1706000003000},
    {"id": 5, "name": "Charlie Brown", "email": "charlie@example.com", "created_at": 1706000004000, "updated_at": 1706000004000, "__op": "c", "__ts_ms": 1706000004000},
]

products_data = [
    {"id": 1, "name": "Laptop", "price": 999.99, "category": "Electronics", "created_at": 1706000000000, "updated_at": 1706000000000, "__op": "c", "__ts_ms": 1706000000000},
    {"id": 2, "name": "Phone", "price": 699.99, "category": "Electronics", "created_at": 1706000001000, "updated_at": 1706000001000, "__op": "c", "__ts_ms": 1706000001000},
    {"id": 3, "name": "Desk", "price": 299.99, "category": "Furniture", "created_at": 1706000002000, "updated_at": 1706000002000, "__op": "c", "__ts_ms": 1706000002000},
    {"id": 4, "name": "Chair", "price": 149.99, "category": "Furniture", "created_at": 1706000003000, "updated_at": 1706000003000, "__op": "c", "__ts_ms": 1706000003000},
    {"id": 5, "name": "Headphones", "price": 199.99, "category": "Electronics", "created_at": 1706000004000, "updated_at": 1706000004000, "__op": "c", "__ts_ms": 1706000004000},
]

orders_data = [
    {"id": 1, "user_id": 1, "product_id": 1, "quantity": 1, "total_amount": 999.99, "status": "completed", "created_at": 1706000003000, "updated_at": 1706000003000, "__op": "c", "__ts_ms": 1706000003000},
    {"id": 2, "user_id": 2, "product_id": 2, "quantity": 2, "total_amount": 1399.98, "status": "pending", "created_at": 1706000004000, "updated_at": 1706000004000, "__op": "c", "__ts_ms": 1706000004000},
    {"id": 3, "user_id": 3, "product_id": 3, "quantity": 1, "total_amount": 299.99, "status": "completed", "created_at": 1706000005000, "updated_at": 1706000005000, "__op": "c", "__ts_ms": 1706000005000},
    {"id": 4, "user_id": 1, "product_id": 4, "quantity": 2, "total_amount": 299.98, "status": "shipped", "created_at": 1706000006000, "updated_at": 1706000006000, "__op": "c", "__ts_ms": 1706000006000},
    {"id": 5, "user_id": 4, "product_id": 5, "quantity": 1, "total_amount": 199.99, "status": "completed", "created_at": 1706000007000, "updated_at": 1706000007000, "__op": "c", "__ts_ms": 1706000007000},
]

update_event = {"id": 1, "name": "John Doe Updated", "email": "john.updated@example.com", "created_at": 1706000000000, "updated_at": 1706000008000, "__op": "u", "__ts_ms": 1706000008000}
delete_event = {"id": 5, "name": "Charlie Brown", "email": "charlie@example.com", "created_at": 1706000004000, "updated_at": 1706000009000, "__op": "d", "__ts_ms": 1706000009000}

uploaded_count = 0
for table, data in [("users", users_data), ("products", products_data), ("orders", orders_data)]:
    for i, record in enumerate(data):
        key = f"raw/{table}/record_{i}.json"
        s3.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=json.dumps(record),
            ContentType='application/json'
        )
        print(f"Uploaded: s3://{BUCKET}/{key}")
        uploaded_count += 1

key = "users/update_record.json"
s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(update_event), ContentType='application/json')
print(f"Uploaded: s3://{BUCKET}/{key}")
uploaded_count += 1

key = "users/delete_record.json"
s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(delete_event), ContentType='application/json')
print(f"Uploaded: s3://{BUCKET}/{key}")
uploaded_count += 1

print("-" * 50)
print(f"Total records uploaded: {uploaded_count}")

