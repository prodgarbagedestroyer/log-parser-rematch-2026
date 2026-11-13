package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"strconv"
	"time"
)

type serviceResult struct {
	Count      int64 `json:"count"`
	Errors     int64 `json:"errors"`
	LatencySum int64 `json:"latency_sum"`
}

type result struct {
	Lines      int64                     `json:"lines"`
	Valid      int64                     `json:"valid"`
	Invalid    int64                     `json:"invalid"`
	LatencySum int64                     `json:"latency_sum"`
	Errors     int64                     `json:"errors"`
	Services   map[string]*serviceResult `json:"services"`
}

type output struct {
	Pass      int    `json:"pass"`
	ElapsedNS int64  `json:"elapsed_ns"`
	Result    result `json:"result"`
}

func newResult() result { return result{Services: make(map[string]*serviceResult)} }

func isDigit(b byte) bool { return b >= '0' && b <= '9' }

func validName(s []byte, max int) bool {
	if len(s) == 0 || len(s) > max {
		return false
	}
	for _, b := range s {
		if !((b >= 'a' && b <= 'z') || (b >= 'A' && b <= 'Z') ||
			(b >= '0' && b <= '9') || b == '_' || b == '-') {
			return false
		}
	}
	return true
}

func validTimestamp(s []byte) bool {
	if len(s) != 20 || s[4] != '-' || s[7] != '-' || s[10] != 'T' ||
		s[13] != ':' || s[16] != ':' || s[19] != 'Z' {
		return false
	}
	for i, b := range s {
		if i != 4 && i != 7 && i != 10 && i != 13 && i != 16 && i != 19 && !isDigit(b) {
			return false
		}
	}
	return true
}

func validLevel(s []byte) bool {
	return string(s) == "DEBUG" || string(s) == "INFO" || string(s) == "WARN" || string(s) == "ERROR"
}

func parseLatency(s []byte) (int64, bool) {
	if len(s) < 1 || len(s) > 7 {
		return 0, false
	}
	var n int64
	for _, b := range s {
		if !isDigit(b) {
			return 0, false
		}
		n = n*10 + int64(b-'0')
	}
	return n, n <= 1_000_000
}

func isDelimiter(b byte) bool { return b == ' ' || b == '\t' }

// parseTokens applies the common validation path to either tokenization variant.
func parseTokens(next func() []byte, r *result) {
	timestamp, service, level, event := next(), next(), next(), next()
	if timestamp == nil || service == nil || level == nil || event == nil ||
		!validTimestamp(timestamp) || !validName(service, 32) || !validLevel(level) || !validName(event, 48) {
		r.Invalid++
		return
	}
	latency := int64(0)
	latencySeen := false
	for token := next(); token != nil; token = next() {
		eq := -1
		for i, b := range token {
			if b == '=' {
				if eq >= 0 {
					r.Invalid++
					return
				}
				eq = i
			}
		}
		if eq <= 0 || eq == len(token)-1 {
			r.Invalid++
			return
		}
		if string(token[:eq]) == "latency_ms" {
			if latencySeen {
				r.Invalid++
				return
			}
			var ok bool
			latency, ok = parseLatency(token[eq+1:])
			if !ok {
				r.Invalid++
				return
			}
			latencySeen = true
		}
	}
	if !latencySeen {
		r.Invalid++
		return
	}
	serviceKey := string(service)
	s := r.Services[serviceKey]
	if s == nil {
		s = &serviceResult{}
		r.Services[serviceKey] = s
	}
	r.Valid++
	r.LatencySum += latency
	s.Count++
	s.LatencySum += latency
	if string(level) == "ERROR" {
		r.Errors++
		s.Errors++
	}
}

func splitNext(line []byte) func() []byte {
	tokens := make([][]byte, 0, 8)
	start := -1
	for i := 0; i <= len(line); i++ {
		if i == len(line) || isDelimiter(line[i]) {
			if start >= 0 {
				tokens = append(tokens, line[start:i])
				start = -1
			}
		} else if start < 0 {
			start = i
		}
	}
	i := 0
	return func() []byte {
		if i == len(tokens) {
			return nil
		}
		token := tokens[i]
		i++
		return token
	}
}

func scanNext(line []byte) func() []byte {
	i := 0
	return func() []byte {
		for i < len(line) && isDelimiter(line[i]) {
			i++
		}
		if i == len(line) {
			return nil
		}
		start := i
		for i < len(line) && !isDelimiter(line[i]) {
			i++
		}
		return line[start:i]
	}
}

// processLine owns the physical-line count and then validates a token slice.
func processLine(line []byte, r *result, scan bool) {
	r.Lines++
	for _, b := range line {
		if b >= 0x80 {
			r.Invalid++
			return
		}
	}
	if scan {
		parseTokens(scanNext(line), r)
		return
	}
	parseTokens(splitNext(line), r)
}

func parsePass(input []byte, scan bool) result {
	r := newResult()
	for start := 0; start < len(input); {
		end := start
		for end < len(input) && input[end] != '\n' {
			end++
		}
		line := input[start:end]
		if end < len(input) && len(line) > 0 && line[len(line)-1] == '\r' {
			line = line[:len(line)-1]
		}
		processLine(line, &r, scan)
		if end == len(input) {
			break
		}
		start = end + 1
	}
	return r
}

func main() {
	if len(os.Args) != 5 {
		fmt.Fprintln(os.Stderr, "usage: parser <input-path> <split|scan> <warmup-count> <measured-count>")
		os.Exit(2)
	}
	mode := os.Args[2]
	if mode != "split" && mode != "scan" {
		fmt.Fprintln(os.Stderr, "variant must be split or scan")
		os.Exit(2)
	}
	warmups, err1 := strconv.Atoi(os.Args[3])
	measured, err2 := strconv.Atoi(os.Args[4])
	if err1 != nil || err2 != nil || warmups < 0 || measured < 0 {
		fmt.Fprintln(os.Stderr, "warmup-count and measured-count must be nonnegative integers")
		os.Exit(2)
	}
	input, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	scan := mode == "scan"
	for i := 0; i < warmups; i++ {
		runtime.KeepAlive(parsePass(input, scan))
	}
	out := bufio.NewWriter(os.Stdout)
	defer out.Flush()
	enc := json.NewEncoder(out)
	for i := 0; i < measured; i++ {
		started := time.Now()
		r := parsePass(input, scan)
		elapsed := time.Since(started).Nanoseconds()
		if err := enc.Encode(output{Pass: i, ElapsedNS: elapsed, Result: r}); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		if err := out.Flush(); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}
}
