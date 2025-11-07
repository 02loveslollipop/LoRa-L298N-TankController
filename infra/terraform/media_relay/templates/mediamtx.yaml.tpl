logLevel: ${log_level}

authMethod: internal
authInternalUsers:
  - user: "${publish_user}"
    pass: "${publish_pass}"
    permissions:
      - action: publish
        path: robot
%{ if viewer_user != "" }
  - user: "${viewer_user}"
    pass: "${viewer_pass}"
    permissions:
      - action: read
        path: robot
      - action: playback
        path: robot
%{ endif }
  - user: any
    pass:
    ips: ['127.0.0.1', '::1']
    permissions:
      - action: api
      - action: metrics
      - action: pprof

rtsp: yes
rtspAddress: :8554

rtmp: yes
rtmpAddress: :1935

hls: yes
hlsAddress: :8888
hlsVariant: lowLatency
hlsSegmentDuration: 1s
hlsPartDuration: 200ms

webrtc: yes
webrtcAddress: :8889
webrtcAllowOrigin: '*'
webrtcLocalUDPAddress: :8200
webrtcICEServers2:
  - url: stun:stun.l.google.com:19302

metrics: yes
metricsAddress: :9998

pprof: yes
pprofAddress: :9999

paths:
  robot:
    source: publisher
    overridePublisher: yes
