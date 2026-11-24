# Bash-Vervollständigung für lernsperre
_lernsperre() {
    local cur prev cmds
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    cmds="status lock pause resume bonus reset edit config reset-config reload detect-ankis use-anki quit start json run hilfe"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=($(compgen -W "$cmds" -- "$cur"))
    elif [ "$COMP_CWORD" -eq 2 ] && [ "$prev" = "pause" ]; then
        COMPREPLY=($(compgen -W "15 30 60" -- "$cur"))
    elif [ "$COMP_CWORD" -eq 2 ] && [ "$prev" = "bonus" ]; then
        COMPREPLY=($(compgen -W "an aus" -- "$cur"))
    elif [ "$COMP_CWORD" -eq 2 ] && [ "$prev" = "reset-config" ]; then
        COMPREPLY=($(compgen -W "--behalten" -- "$cur"))
    elif [ "$COMP_CWORD" -eq 2 ] && [ "$prev" = "use-anki" ]; then
        COMPREPLY=($(compgen -W "1 2 3 4 5" -- "$cur"))
    fi
}
complete -F _lernsperre lernsperre
