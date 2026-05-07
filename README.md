# TZBot

## TZBot API Documentation

The DiscordTZ API Server operates over the UDP protocol. It uses a custom binary header for packet framing, followed by a payload that can be JSON or MsgPack, optionally compressed and/or encrypted.

### Connection Details

*   **Protocols**: UDP (TCP is for an optional honeypot)
*   **Port**: Defined in server configuration (default varies).
*   **Endianness**: Big-Endian (`>`) for all binary headers.

---

### Packet Structure

#### Request Header (Client → Server)
The request header is **7 bytes** long.

| Offset | Size | Type     | Description                                                       |
|:-------|:-----|:---------|:------------------------------------------------------------------|
| 0      | 1    | `char`   | Magic Byte `'t'` (0x74)                                           |
| 1      | 1    | `char`   | Magic Byte `'z'` (0x7A)                                           |
| 2      | 1    | `uint8`  | **Data Offset**. Usually `7`. The index where the payload begins. |
| 3      | 1    | `uint8`  | **Request Type ID**. Identifies the endpoint (see below).         |
| 4      | 1    | `uint8`  | **Flags**. Bitmask for encryption/compression.                    |
| 5      | 2    | `uint16` | **Content Length**. Length of the payload in bytes.               |

#### Response Header (Server -> Client)
The response header is **6 bytes** long.

| Offset | Size | Type     | Description                                         |
|:-------|:-----|:---------|:----------------------------------------------------|
| 0      | 1    | `char`   | Magic Byte `'t'` (0x74)                             |
| 1      | 1    | `char`   | Magic Byte `'z'` (0x7A)                             |
| 2      | 1    | `uint8`  | **Header Length**. Usually `6`.                     |
| 3      | 1    | `uint8`  | **Flags**. Bitmask describing the response payload. |
| 4      | 2    | `uint16` | **Content Length**. Length of the response payload. |

---

### Flags & Payload Processing

The `Flags` byte determines how the payload is encoded. Flags can be combined.

| Flag Name  | Value           | Description                                                                 |
|:-----------|:----------------|:----------------------------------------------------------------------------|
| `AES`      | `0x01` (1 << 0) | Payload is encrypted using AES-256-GCM. Header is verified using AAD.       |
| `CHACHA20` | `0x02` (1 << 1) | Payload is encrypted using ChaCha20-Poly1305. Header is verified using AAD. |
| `MSGPACK`  | `0x08` (1 << 3) | Payload is MsgPack encoded. If not set, payload is JSON.                    |

**Processing Order (Sending):**
1. Encode data (JSON or MsgPack).
2. Encrypt (AES-256-GCM xor ChaCha20-Poly1305) if flag set.
3. Prepend Header.

**Processing Order (Receiving):**
1. Parse Header.
2. Decrypt (AES-256-GCM xor ChaCha20-Poly1305) if flag set.
3. Decode (JSON or MsgPack).

---

### Request Payload Format

After decoding, the request payload must be a JSON object (or MsgPack map) with the following structure:

*   **apiKey**: Required for most endpoints.
*   **data**: A dictionary containing the specific parameters for the Request Type. Optional if empty

### Response Payload Format

The server responds with a JSON object (or MsgPack map) wrapped in the Response Header.
**Common Status Codes:**
*   `200`: OK
*   `400`: Bad Request
*   `403`: Forbidden (Invalid Key or Permissions)
*   `404`: Not Found
*   `409`: Conflict
*   `500`: Internal Server Error

---

### Endpoints

#### 0. Ping
*   **ID**: `0`
*   **Permissions**: None
*   **Description**: Checks server connectivity.
*   **Request Data**: `{}`
*   **Response**: `"Pong"`

#### 1. Get Timezone from User ID
*   **ID**: `1`
*   **Permissions**: `DISCORD_ID` (1)
*   **Description**: Retrieves the timezone registered to a Discord User ID.
*   **Request Data**: `{"userId": <val>}`
*   **Response**: Timezone string (e.g., `"Europe/London"`) or `404`.

### 2. Get Timezone from IP
*   **ID**: `2`
*   **Permissions**: `IP_ADDRESS` (16)
*   **Description**: Geolocates an IP address to a timezone. If the IP provided is local, it'll return the timezone of the IP requesting.
*   **Request Data**: `{"ip": <val>}`
*   **Response**: Timezone string or `404`.

### 3. Link User ID to UUID
*   **ID**: `3`
*   **Permissions**: `UUID_POST` (8)
*   **Description**: Initiates a link between a Minecraft UUID and a Timezone. Returns a verification code.
*   **Request Data**: `{"uuid": <val1>, "timezone": <val2>}`
*   **Response**: Verification Code (string) or `409` (Conflict).

### 4. Get Timezone from UUID
*   **ID**: `4`
*   **Permissions**: `MINECRAFT_UUID` (4)
*   **Description**: Retrieves the timezone registered to a Minecraft UUID.
*   **Request Data**: `{"uuid": <val>}`
*   **Response**: Verification Code (string) or `409` (Conflict).

### 5. Is Linked
*   **ID**: `5`
*   **Permissions**: `MINECRAFT_UUID` (4)
*   **Description**: Checks if a UUID is linked and returns the associated Discord Username.
*   **Request Data**: `{"uuid": <val>}`
*   **Response**: Discord Username (string) or `404`.

### 6. Get User ID from UUID
*   **ID**: `6`
*   **Permissions**: `MINECRAFT_UUID` (4) + `DISCORD_ID` (1)
*   **Description**: Retrieves the Discord User ID associated with a Minecraft UUID.
*   **Request Data**: `{"uuid": <val>}`
*   **Response**: Discord User ID (int) or `404`.

### 7. Get UUID from User ID
*   **ID**: `7`
*   **Permissions**: Valid API Key
*   **Description**: Retrieves the Minecraft UUID associated with a Discord User ID.
*   **Request Data**: `{"userId": <val>}`
*   **Response**: UUID (string) or `404`.
 
### 8. Update Timezone
*   **ID**: `8`
*   **Permissions**: `UUID_POST` (8)
*   **Description**: Updates UUID's timezone to the specified one.
*   **Request Data**: `{"uuid": <val1>, "timezone": <val2>}`
*   **Response**: `200` if modification was successful, `404` if UUID was not found, `500` if the change failed.