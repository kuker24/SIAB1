FROM golang:1.25-alpine AS build
WORKDIR /src
ENV GOPROXY=https://proxy.golang.org,direct \
    GOTOOLCHAIN=local
COPY go/ .
ARG BIN=server
ARG REVISION=unknown
RUN CGO_ENABLED=0 GOOS=linux go build -mod=readonly -trimpath -buildvcs=false \
    -ldflags="-s -w -buildid= -X main.revision=${REVISION}" \
    -o /out/app ./cmd/${BIN}

FROM alpine:3.20
ARG REVISION=unknown
LABEL org.opencontainers.image.revision="${REVISION}"
WORKDIR /app
RUN apk add --no-cache ca-certificates tzdata wget
COPY --from=build /out/app /app/app
EXPOSE 8000
ENTRYPOINT ["/app/app"]
