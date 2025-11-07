${domain_name} {
  encode gzip

  @hls path /hls*
  reverse_proxy @hls http://127.0.0.1:8888

  reverse_proxy * http://127.0.0.1:8889
}
