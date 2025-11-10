//go:build cpu
// +build cpu

package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"
)

type cpuStreamerConfig struct {
	ffmpegBinary    string
	cameraDevice    string
	audioDevice     string
	frameRate       string
	frameRateInt    int
	resolution      string
	videoBitrate    string
	videoMaxRate    string
	videoBufSize    string
	videoPreset     string
	streamName      string
	targetHost      string
	publishUser     string
	publishPass     string
	rtspTransport   string
	inputFormat     string
	audioBitrate    string
	audioSampleRate string
	audioChannels   string
	generateTone    bool
}

func main() {
	cfg := loadCPUConfig()
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	logger := log.New(os.Stdout, "cpu-streamer: ", log.LstdFlags|log.Lmicroseconds)
	logger.Printf("starting CPU streamer with camera=%s target=%s stream=%s", cfg.cameraDevice, cfg.targetHost, cfg.streamName)

	retryDelay := 3 * time.Second
	for {
		err := runCPUFFmpeg(ctx, cfg, logger)
		if ctx.Err() != nil {
			logger.Println("shutdown requested, exiting")
			return
		}
		if err != nil {
			logger.Printf("ffmpeg exited: %v", err)
		}
		logger.Printf("retrying in %s", retryDelay)
		select {
		case <-time.After(retryDelay):
		case <-ctx.Done():
			logger.Println("shutdown requested during backoff, exiting")
			return
		}
	}
}

func loadCPUConfig() cpuStreamerConfig {
	frameRate := readEnv("FRAME_RATE", "30")
	frameRateInt := parsePositiveInt(frameRate, 30)
	return cpuStreamerConfig{
		ffmpegBinary:    readEnv("FFMPEG_CPU_BINARY", "ffmpeg"),
		cameraDevice:    readEnv("CAMERA_DEVICE", "/dev/video0"),
		audioDevice:     os.Getenv("AUDIO_DEVICE"),
		frameRate:       frameRate,
		frameRateInt:    frameRateInt,
		resolution:      readEnv("VIDEO_SIZE", "1280x720"),
		videoBitrate:    readEnv("VIDEO_BITRATE", "2M"),
		videoMaxRate:    readEnv("VIDEO_MAXRATE", "2M"),
		videoBufSize:    readEnv("VIDEO_BUFSIZE", "2M"),
		videoPreset:     readEnv("X264_PRESET", "ultrafast"),
		streamName:      readEnv("STREAM_NAME", "robot"),
		targetHost:      readEnv("RELAY_HOST", "rtsp.nene.02labs.me:8554"),
		publishUser:     readEnv("RELAY_PUBLISH_USER", ""),
		publishPass:     readEnv("RELAY_PUBLISH_PASS", ""),
		rtspTransport:   readEnv("RTSP_TRANSPORT", "tcp"),
		inputFormat:     os.Getenv("INPUT_FORMAT"),
		audioBitrate:    readEnv("AUDIO_BITRATE", "128k"),
		audioSampleRate: readEnv("AUDIO_SAMPLE_RATE", "48000"),
		audioChannels:   readEnv("AUDIO_CHANNELS", "2"),
		generateTone:    readEnvBool("GENERATE_SINE_AUDIO", true),
	}
}

func runCPUFFmpeg(ctx context.Context, cfg cpuStreamerConfig, logger *log.Logger) error {
	args := buildCPUFFmpegArgs(cfg)
	logger.Printf("launching ffmpeg (%d args)", len(args))

	cmd := exec.CommandContext(ctx, cfg.ffmpegBinary, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to start ffmpeg: %w", err)
	}

	return cmd.Wait()
}

func buildCPUFFmpegArgs(cfg cpuStreamerConfig) []string {
	args := []string{"-re"}

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

	if cfg.audioDevice != "" {
		args = append(args,
			"-f", "alsa",
			"-thread_queue_size", "256",
			"-i", cfg.audioDevice,
		)
	} else if cfg.generateTone {
		args = append(args,
			"-f", "lavfi",
			"-i", fmt.Sprintf("sine=frequency=1000:sample_rate=%s", cfg.audioSampleRate),
		)
	}

	args = append(args,
		"-c:v", "libx264",
		"-preset", cfg.videoPreset,
		"-tune", "zerolatency",
		"-g", strconv.Itoa(cfg.frameRateInt),
		"-keyint_min", strconv.Itoa(cfg.frameRateInt),
		"-bf", "0",
		"-pix_fmt", "yuv420p",
		"-b:v", cfg.videoBitrate,
		"-maxrate", cfg.videoMaxRate,
		"-bufsize", cfg.videoBufSize,
	)

	if cfg.audioDevice != "" || cfg.generateTone {
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
		buildCPURTSPURL(cfg),
	)

	return args
}

func buildCPURTSPURL(cfg cpuStreamerConfig) string {
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

func parsePositiveInt(value string, fallback int) int {
	if value == "" {
		return fallback
	}
	v, err := strconv.Atoi(value)
	if err != nil || v <= 0 {
		log.Printf("invalid positive int %q, using fallback %d", value, fallback)
		return fallback
	}
	return v
}
