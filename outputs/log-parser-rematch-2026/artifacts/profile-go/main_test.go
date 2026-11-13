package main

import (
	"os"
	"testing"
)

var benchmarkCorpus []byte
var benchmarkResult result

func init() {
	var err error
	benchmarkCorpus, err = os.ReadFile("../../datasets/clean.log")
	if err != nil {
		panic(err)
	}
}

func BenchmarkSplit(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		benchmarkResult = parsePass(benchmarkCorpus, false)
	}
}

func BenchmarkScan(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		benchmarkResult = parsePass(benchmarkCorpus, true)
	}
}
