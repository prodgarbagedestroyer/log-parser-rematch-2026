use std::collections::HashMap;
use std::env;
use std::fs;
use std::io::{self, BufWriter, Write};
use std::time::Instant;

#[derive(Default)]
struct ServiceResult {
    count: u64,
    errors: u64,
    latency_sum: u64,
}

#[derive(Default)]
struct ResultData {
    lines: u64,
    valid: u64,
    invalid: u64,
    latency_sum: u64,
    errors: u64,
    services: HashMap<String, ServiceResult>,
}

fn is_digit(b: u8) -> bool {
    b.is_ascii_digit()
}

fn valid_name(s: &[u8], max: usize) -> bool {
    !s.is_empty()
        && s.len() <= max
        && s.iter().all(|b| b.is_ascii_alphanumeric() || *b == b'_' || *b == b'-')
}

fn valid_timestamp(s: &[u8]) -> bool {
    if s.len() != 20
        || s[4] != b'-'
        || s[7] != b'-'
        || s[10] != b'T'
        || s[13] != b':'
        || s[16] != b':'
        || s[19] != b'Z'
    {
        return false;
    }
    s.iter().enumerate().all(|(i, b)| {
        matches!(i, 4 | 7 | 10 | 13 | 16 | 19) || is_digit(*b)
    })
}

fn valid_level(s: &[u8]) -> bool {
    matches!(s, b"DEBUG" | b"INFO" | b"WARN" | b"ERROR")
}

fn parse_latency(s: &[u8]) -> Option<u64> {
    if s.is_empty() || s.len() > 7 || !s.iter().all(|b| is_digit(*b)) {
        return None;
    }
    let mut n = 0u64;
    for b in s {
        n = n * 10 + u64::from(b - b'0');
    }
    (n <= 1_000_000).then_some(n)
}

fn parse_tokens<'a, I>(mut tokens: I, r: &mut ResultData)
where
    I: Iterator<Item = &'a [u8]>,
{
    let (Some(timestamp), Some(service), Some(level), Some(event)) =
        (tokens.next(), tokens.next(), tokens.next(), tokens.next())
    else {
        r.invalid += 1;
        return;
    };
    if !valid_timestamp(timestamp)
        || !valid_name(service, 32)
        || !valid_level(level)
        || !valid_name(event, 48)
    {
        r.invalid += 1;
        return;
    }

    let mut latency = None;
    for token in tokens {
        let mut equals = token.iter().enumerate().filter(|(_, b)| **b == b'=');
        let Some((eq, _)) = equals.next() else {
            r.invalid += 1;
            return;
        };
        if equals.next().is_some() || eq == 0 || eq + 1 == token.len() {
            r.invalid += 1;
            return;
        }
        if &token[..eq] == b"latency_ms" {
            if latency.is_some() {
                r.invalid += 1;
                return;
            }
            let Some(value) = parse_latency(&token[eq + 1..]) else {
                r.invalid += 1;
                return;
            };
            latency = Some(value);
        }
    }
    let Some(latency) = latency else {
        r.invalid += 1;
        return;
    };

    let key = String::from_utf8(service.to_vec()).expect("service is ASCII validated");
    let stats = r.services.entry(key).or_default();
    r.valid += 1;
    r.latency_sum += latency;
    stats.count += 1;
    stats.latency_sum += latency;
    if level == b"ERROR" {
        r.errors += 1;
        stats.errors += 1;
    }
}

fn process_line(line: &[u8], r: &mut ResultData, scan: bool) {
    r.lines += 1;
    if !line.is_ascii() {
        r.invalid += 1;
        return;
    }
    if scan {
        // The scan path advances through token boundaries and never collects them.
        parse_tokens(line.split(|b| *b == b' ' || *b == b'\t').filter(|t| !t.is_empty()), r);
    } else {
        // The split path deliberately materializes this line's complete token vector.
        let tokens: Vec<&[u8]> = line
            .split(|b| *b == b' ' || *b == b'\t')
            .filter(|t| !t.is_empty())
            .collect();
        parse_tokens(tokens.into_iter(), r);
    }
}

fn parse_pass(input: &[u8], scan: bool) -> ResultData {
    let mut r = ResultData::default();
    let mut start = 0usize;
    while start < input.len() {
        let end = input[start..]
            .iter()
            .position(|b| *b == b'\n')
            .map(|p| start + p)
            .unwrap_or(input.len());
        let mut line = &input[start..end];
        if end < input.len() && line.last() == Some(&b'\r') {
            line = &line[..line.len() - 1];
        }
        process_line(line, &mut r, scan);
        if end == input.len() {
            break;
        }
        start = end + 1;
    }
    r
}

fn print_result<W: Write>(mut out: W, pass: usize, elapsed_ns: u64, r: &ResultData) -> io::Result<()> {
    write!(
        out,
        "{{\"pass\":{pass},\"elapsed_ns\":{elapsed_ns},\"result\":{{\"lines\":{},\"valid\":{},\"invalid\":{},\"latency_sum\":{},\"errors\":{},\"services\":{{",
        r.lines, r.valid, r.invalid, r.latency_sum, r.errors
    )?;
    let mut first = true;
    for (service, stats) in &r.services {
        if !first {
            out.write_all(b",")?;
        }
        first = false;
        // Valid service names contain only JSON-safe ASCII characters.
        write!(
            out,
            "\"{service}\":{{\"count\":{},\"errors\":{},\"latency_sum\":{}}}",
            stats.count, stats.errors, stats.latency_sum
        )?;
    }
    out.write_all(b"}}}\n")
}

fn parse_count(s: &str, name: &str) -> usize {
    match s.parse::<usize>() {
        Ok(n) => n,
        Err(_) => {
            eprintln!("{name} must be a nonnegative integer");
            std::process::exit(2);
        }
    }
}

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 5 {
        eprintln!("usage: parser <input-path> <split|scan> <warmup-count> <measured-count>");
        std::process::exit(2);
    }
    let scan = match args[2].as_str() {
        "split" => false,
        "scan" => true,
        _ => {
            eprintln!("variant must be split or scan");
            std::process::exit(2);
        }
    };
    let warmups = parse_count(&args[3], "warmup-count");
    let measured = parse_count(&args[4], "measured-count");
    let input = fs::read(&args[1])?;
    for _ in 0..warmups {
        std::hint::black_box(parse_pass(&input, scan));
    }
    let stdout = io::stdout();
    let mut out = BufWriter::new(stdout.lock());
    for pass in 0..measured {
        let started = Instant::now();
        let r = parse_pass(&input, scan);
        let elapsed_ns = started.elapsed().as_nanos() as u64;
        print_result(&mut out, pass, elapsed_ns, &r)?;
        out.flush()?;
        std::hint::black_box(&r);
    }
    Ok(())
}
