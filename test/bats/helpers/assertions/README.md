# bats-assert
Assertion library for BATS (Bash Automated Testing System)

## Installation

Recommended installation is via git submodule. Assuming your project's bats
tests are in `test`:

``` sh
git submodule add https://github.com/jasonkarns/bats-assert test/helpers/assertions
git commit -am 'added bats-assert module'
```

then in `test/test_helper.bash`:

``` bash
load helpers/assertions/all
```

(Optionally configure [sparse-checkout](http://git-scm.com/docs/git-read-tree#_sparse_checkout) if you're concerned with all the non-essential files being in your repo)

Also available as an [npm module](https://www.npmjs.com/package/bats-assert) if you're into that sort of thing.

``` sh
npm install --save-dev bats-assert
```

then in `test/test_helper.bash`:

``` bash
load ../node_modules/bats-assert/all
```

## Assertion API

### flunk
forces a test failure with an optional message

``` bash
flunk
# or
flunk "expected blue skies"
```

### assert
asserts command returns successfully

``` bash
assert my-command
assert [ 2 -eq 2 ]
```

### refute
asserts command returns unsuccessfully

``` bash
refute invalid-command
refute [ 2 -eq 3 ]
```

### assert_success
asserts successful exit `$status` with (optional) `$output`

``` bash
run my-command

assert_success
# or
assert_success "expected output"
```

### assert_failure
asserts unsuccessful exit `$status` with (optional) `$output`

``` bash
run my-command

assert_failure
# or
assert_failure "expected output"
```

### assert_equal
asserts equality

``` bash
actual="$(my-command)"
expected="my results"

assert_equal expected actual
```

### assert_contains
asserts x contains y

```
assert_contains foobar oo
```

### refute_contains
asserts x does not contain y

```
refute_contains foobar baz
```

### assert_starts_with
asserts x starts with y

```
assert_starts_with foobar foo
```

### assert_output
asserts `$output`

```
run my-command

assert_output "my results"
```

### assert_output_contains
asserts `$output` contains argument

```
run my-command

assert_output_contains "results"
```

### refute_output_contains
asserts `$output` does not contain argument

```
run my-command

refute_output_contains "unicorn"
```

### assert_line
asserts `$output` contains given line (at optional line index)

```
run my-command

assert_line "my results"
# or
assert_line 0 "my results"
```

### refute_line
asserts `$output` does *not* contain given line

```
run my-command

refute_line "thirsty rando"
```

## Credits

Assertion functions taken from the test_helpers of [rbenv][], [ruby-build][],
and [rbenv-aliases][]. Many thanks to their authors and contributors: [Sam
Stephenson](https://github.com/sstephenson), [Mislav
Marohnić](https://github.com/mislav), and [Tim Pope](https://github.com/tpope).

[rbenv]:https://github.com/sstephenson/rbenv
[ruby-build]:https://github.com/sstephenson/ruby-build
[rbenv-aliases]:https://github.com/tpope/rbenv-aliases
