#! /bin/bash

set -e

org="$1"
project="$2"
repo_url="$3"
githash="$4"
apiEndpoint="$5"
apiKey="$6"


parser() {
  line="$1"
  if (echo "$line" | grep 'git\|+'); then
    echo "Can't parse VCS yet"
    return 1
  fi
  package=$(echo "$line" | awk -F '[<>~=\[! ]' '{print $1}')
  operator=$(echo "$line" | grep -o '\([<>]=\?\)\|\(==\|!=\|~\)')
  version=$(echo "$line" | grep '[<>~=! ]' | sed '/ \?\[.*\]/s///p' | awk -F '[<>~=! ]' '{print $NF}')
  json=$(jq -ncS \
    --arg package "$package" \
    --arg operator "$operator" \
    --arg version "$version" \
    --arg org "$org" \
    --arg project "$project" \
    --arg githash "$githash" \
    '{
      "commit": $githash,
      "organization": $org,
      "project": $project,
      "language": "python",
      "operator": $operator,
      "name": $package,
      "packageManager": "pip",
      "version": $version
    }
    | del(.[] | select(. == ""))' # remove keys with empty values
  )
  echo "$json" >> /tmp/pkglist
  return 0
}

export -f parser
export githash org project
# echo '[' > /tmp/pkglist
echo '' > /tmp/pkglist
# shellcheck disable=SC2038
find . -name requirements.txt -exec cat {} \; | xargs -L 1 -I {} bash -i -c "parser {}"
# echo ']' >> /tmp/pkglist
< /tmp/pkglist tr ' ' _ | jq -n \
  --arg org "$org" \
  --arg project "$project" \
  --arg githash "$githash" \
  --arg scmUrl "$repo_url" \
  '{
    "organization": $org,
    "project": $project,
    "commit": $githash,
    "scmUrl": $scmUrl,
    "packages": [inputs]
  }' > /tmp/jsonLoad

curl -H "x-api-key: $apiKey" -H "Content-Type: application/json" -X POST -d @/tmp/jsonLoad "$apiEndpoint"
