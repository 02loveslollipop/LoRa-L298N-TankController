${domain_name} {
  encode gzip

  header Access-Control-Allow-Origin "*"
  header Access-Control-Allow-Methods "GET, POST, OPTIONS, PATCH"
  header Access-Control-Allow-Headers "Content-Type, Accept"

  @preflight {
    method OPTIONS
  }
  respond @preflight "" 204

  @hls path /hls*
  reverse_proxy @hls http://127.0.0.1:8888

  reverse_proxy * http://127.0.0.1:8889
}
