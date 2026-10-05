#include <string.h>

/* "key=value" 한 줄을 key와 value로 나눈다. '='가 없으면 -1, 있으면 0. */
int parse_line(char *line, char **key, char **value) {
    char *eq = strchr(line, '=');
    if (eq == NULL) {
        return -1;
    }
    *eq = '\0';
    *key = line;
    *value = eq + 1;
    return 0;
}
