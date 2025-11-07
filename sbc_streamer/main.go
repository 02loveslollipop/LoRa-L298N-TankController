package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

type streamerConfig struct {
	ffmpegBinary      string
	cameraDevice      string
	audioDevice       string
	frameRate         string
	resolution        string
	videoBitrate      string
	videoMaxRate      string
	videoBufSize      string
	videoCodec        string
	videoFormat       string
	streamName        string
	targetHost        string
	publishUser       string
	publishPass       string
	rtspTransport     string
	inputFormat       string
	audioBitrate      string
	audioSampleRate   string
	audioChannels     string
	sineFrequency     string
	generateSineAudio bool
	useTestPattern    bool
}

func main() {
	cfg := loadConfig()
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	logger := log.New(os.Stdout, "streamer: ", log.LstdFlags|log.Lmicroseconds)
	logger.Printf("starting streamer with camera=%s target=%s stream=%s", cfg.cameraDevice, cfg.targetHost, cfg.streamName)
	if cfg.publishUser == "" {
		logger.Println("warning: RELAY_PUBLISH_USER is empty; publishing will fail if the relay requires authentication")
	}
	if cfg.publishUser != "" && cfg.publishPass == "" {
		logger.Println("warning: RELAY_PUBLISH_PASS is empty while RELAY_PUBLISH_USER is set")
	}

	retryDelay := 3 * time.Second

	for {
		err := runFFmpeg(ctx, cfg, logger)
		if ctx.Err() != nil {
			logger.Println("shutdown requested, exiting")
			return
		}
		logger.Printf("ffmpeg exited: %v", err)
		logger.Printf("retrying in %s", retryDelay)
		select {
		case <-time.After(retryDelay):
		case <-ctx.Done():
			logger.Println("shutdown requested during backoff, exiting")
			return
		}
	}
}

func loadConfig() streamerConfig {
	baseBitrate := readEnv("VIDEO_BITRATE", "2M")
	return streamerConfig{
		ffmpegBinary:      readEnv("FFMPEG_BINARY", "ffmpeg"),
		cameraDevice:      readEnv("CAMERA_DEVICE", "/dev/video0"),
		audioDevice:       os.Getenv("AUDIO_DEVICE"),
		frameRate:         readEnv("FRAME_RATE", "30"),
		resolution:        readEnv("VIDEO_SIZE", "1280x720"),
		videoBitrate:      baseBitrate,
		videoMaxRate:      readEnv("VIDEO_MAXRATE", baseBitrate),
		videoBufSize:      readEnv("VIDEO_BUFSIZE", baseBitrate),
		videoCodec:        readEnv("VIDEO_CODEC", "h264_rkmpp"),
		videoFormat:       readEnv("VIDEO_FORMAT", "nv12"),
		streamName:        readEnv("STREAM_NAME", "robot"),
		targetHost:        readEnv("RELAY_HOST", "rtsp.02labs.me:8554"),
		publishUser:       readEnv("RELAY_PUBLISH_USER", ""),
		publishPass:       readEnv("RELAY_PUBLISH_PASS", ""),
		rtspTransport:     readEnv("RTSP_TRANSPORT", "tcp"),
		inputFormat:       os.Getenv("INPUT_FORMAT"),
		audioBitrate:      readEnv("AUDIO_BITRATE", "128k"),
		audioSampleRate:   readEnv("AUDIO_SAMPLE_RATE", "48000"),
		audioChannels:     readEnv("AUDIO_CHANNELS", "2"),
		sineFrequency:     readEnv("SINE_FREQUENCY", "1000"),
		generateSineAudio: readEnvBool("GENERATE_SINE_AUDIO", true),
		useTestPattern:    readEnvBool("USE_TEST_PATTERN", false),
	}
}

func runFFmpeg(ctx context.Context, cfg streamerConfig, logger *log.Logger) error {
	args := buildFFmpegArgs(cfg)
	logger.Printf("launching ffmpeg (%d args)", len(args))

	cmd := exec.CommandContext(ctx, cfg.ffmpegBinary, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to start ffmpeg: %w", err)
	}

	return cmd.Wait()
}

func buildFFmpegArgs(cfg streamerConfig) []string {
	args := []string{"-re"}

	if cfg.useTestPattern {
		args = append(args,
			"-f", "lavfi",
			"-i", fmt.Sprintf("testsrc=size=%s:rate=%s", cfg.resolution, cfg.frameRate),
		)
	} else {
		args = append(args, "-f", "v4l2")
		if cfg.inputFormat != "" {
			args = append(args, "-input_format", cfg.inputFormat)
		}
		args = append(args,
			"-thread_queue_size", "256",
			"-framerate", cfg.frameRate,
			"-video_size", cfg.resolution,
			"-i", cfg.cameraDevice,
		)
	}

	if cfg.audioDevice != "" {
		args = append(args,
			"-f", "alsa",
			"-thread_queue_size", "256",
			"-i", cfg.audioDevice,
		)
	} else if cfg.generateSineAudio {
		args = append(args,
			"-f", "lavfi",
			"-i", fmt.Sprintf("sine=frequency=%s:sample_rate=%s", cfg.sineFrequency, cfg.audioSampleRate),
		)
	}

	args = append(args,
		"-vf", fmt.Sprintf("format=%s", cfg.videoFormat),
		"-c:v", cfg.videoCodec,
		"-b:v", cfg.videoBitrate,
		"-maxrate", cfg.videoMaxRate,
		"-bufsize", cfg.videoBufSize,
	)

	if cfg.audioDevice != "" || cfg.generateSineAudio {
		args = append(args,
			"-c:a", "aac",
			"-b:a", cfg.audioBitrate,
			"-ar", cfg.audioSampleRate,
			"-ac", cfg.audioChannels,
		)
	}

	args = append(args,
		"-rtsp_transport", cfg.rtspTransport,
		"-f", "rtsp",
	)

	rtspURL := buildRTSPURL(cfg)
	return append(args, rtspURL)
}

func buildRTSPURL(cfg streamerConfig) string {
	var auth string
	if cfg.publishUser != "" {
		auth = cfg.publishUser
		if cfg.publishPass != "" {
			auth = fmt.Sprintf("%s:%s", cfg.publishUser, cfg.publishPass)
		}
	}
	if auth != "" {
		auth += "@"
	}
	return fmt.Sprintf("rtsp://%s%s/%s", auth, cfg.targetHost, cfg.streamName)
}

func readEnv(key, fallback string) string {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		return v
	}
	return fallback
}

func readEnvBool(key string, fallback bool) bool {
	v, ok := os.LookupEnv(key)
	if !ok || v == "" {
		return fallback
	}
	switch strings.ToLower(v) {
	case "1", "true", "t", "yes", "y":
		return true
	case "0", "false", "f", "no", "n":
		return false
	default:
		return fallback
	}
}
