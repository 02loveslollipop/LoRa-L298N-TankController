package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"syscall"
	"time"
)

type streamerConfig struct {
	ffmpegBinary  string
	cameraDevice  string
	audioDevice   string
	frameRate     string
	resolution    string
	bitrate       string
	streamName    string
	targetHost    string
	publishUser   string
	publishPass   string
	rtspTransport string
	inputFormat   string
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
	return streamerConfig{
		ffmpegBinary:  readEnv("FFMPEG_BINARY", "ffmpeg"),
		cameraDevice:  readEnv("CAMERA_DEVICE", "/dev/video0"),
		audioDevice:   os.Getenv("AUDIO_DEVICE"),
		frameRate:     readEnv("FRAME_RATE", "30"),
		resolution:    readEnv("VIDEO_SIZE", "1280x720"),
		bitrate:       readEnv("VIDEO_BITRATE", "1500k"),
		streamName:    readEnv("STREAM_NAME", "robot"),
		targetHost:    readEnv("RELAY_HOST", "rtsp.nene.02labs.me:8554"),
		publishUser:   readEnv("RELAY_PUBLISH_USER", ""),
		publishPass:   readEnv("RELAY_PUBLISH_PASS", ""),
		rtspTransport: readEnv("RTSP_TRANSPORT", "tcp"),
		inputFormat:   os.Getenv("INPUT_FORMAT"),
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
	args := []string{
		"-f", "v4l2",
	}
	if cfg.inputFormat != "" {
		args = append(args, "-input_format", cfg.inputFormat)
	}
	args = append(args,
		"-thread_queue_size", "256",
		"-framerate", cfg.frameRate,
		"-video_size", cfg.resolution,
		"-i", cfg.cameraDevice,
	)

	if cfg.audioDevice != "" {
		audioArgs := []string{
			"-f", "alsa",
			"-thread_queue_size", "256",
			"-i", cfg.audioDevice,
		}
		args = append(args, audioArgs...)
	}

	videoOut := []string{
		"-vf", "format=yuv420p",
		"-c:v", "libx264",
		"-preset", "ultrafast",
		"-tune", "zerolatency",
		"-pix_fmt", "yuv420p",
		"-b:v", cfg.bitrate,
		"-maxrate", cfg.bitrate,
		"-bufsize", cfg.bitrate,
		"-g", "60",
		"-keyint_min", "30",
	}
	args = append(args, videoOut...)

	if cfg.audioDevice != "" {
		audioOut := []string{
			"-c:a", "aac",
			"-b:a", "128k",
			"-ar", "48000",
			"-ac", "2",
		}
		args = append(args, audioOut...)
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
