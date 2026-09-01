# Multi annotation page

<!-- test:spread
priority: 300
kill-timeout: 30m
-->

<!-- test:wait --seconds 10 -->

```shell
echo first
```

<!-- test:await-idle --timeout 900 -->

<!-- test:skip -->

```shell
echo skipped
```

<!-- test:run
echo hidden
-->

<!-- test:assert
test -f /tmp/done
-->

```shell
echo last
```
